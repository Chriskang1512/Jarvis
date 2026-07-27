from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

from jarvis.core.events import InMemoryEventBus
from jarvis.memory import (
    MemoryManager,
    MemoryStorePolicy,
    MemoryType,
    SQLiteMemoryProvider,
)
from jarvis.abilities.native.memory.models import MemoryEntry, format_saved_message
from jarvis.runtime.planner import ExecutionPlan, ExecutionStep
from jarvis.runtime.tool_dispatcher.dispatcher import apply_memory_context
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher


class TestMemorySystem(unittest.TestCase):
    def setUp(self):
        root = Path("tmp") / "tests"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "sprint20_memory.db"
        for candidate in (
            self.path,
            self.path.with_name(self.path.name + "-wal"),
            self.path.with_name(self.path.name + "-shm"),
        ):
            if candidate.exists():
                candidate.unlink()

    def tearDown(self):
        for candidate in (
            self.path,
            self.path.with_name(self.path.name + "-wal"),
            self.path.with_name(self.path.name + "-shm"),
        ):
            if candidate.exists():
                candidate.unlink()

    def test_sqlite_provider_persists_structured_memory(self):
        manager = MemoryManager(SQLiteMemoryProvider(self.path))
        manager.store(
            "user.location",
            "강릉",
            MemoryType.LONG_TERM,
            confidence=0.95,
        )

        restored = MemoryManager(SQLiteMemoryProvider(self.path)).retrieve("강릉")

        self.assertEqual(restored.get("user.location"), "강릉")
        self.assertEqual(restored.records[0].memory_type, MemoryType.LONG_TERM)

    def test_working_memory_is_isolated_and_clearable_by_session(self):
        provider = SQLiteMemoryProvider(self.path)
        first = MemoryManager(provider, session_id="session-a")
        second = MemoryManager(provider, session_id="session-b")
        first.remember_working("selected.mail", "message-1")

        self.assertEqual(first.retrieve("message-1").get("selected.mail"), "message-1")
        self.assertEqual(second.retrieve("message-1").get("selected.mail"), "")
        self.assertEqual(first.clear_working(), 1)
        self.assertEqual(first.retrieve("message-1").records, ())

    def test_working_memory_expires_by_ttl(self):
        bus = InMemoryEventBus()
        events = []
        bus.subscribe("*", events.append)
        manager = MemoryManager(
            SQLiteMemoryProvider(self.path),
            session_id="session-expiry",
            event_bus=bus,
        )
        expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        manager.store(
            "selected.mail",
            "message-expired",
            MemoryType.WORKING,
            expires_at=expired_at,
        )

        self.assertEqual(manager.retrieve("message-expired").records, ())
        self.assertEqual(
            [event.event_type for event in events],
            ["MemoryStored", "MemoryDeleted", "MemoryRetrieved"],
        )
        self.assertEqual(events[1].payload["reason"], "ttl_expired")

    def test_memory_events_are_auditable_without_raw_values(self):
        bus = InMemoryEventBus()
        events = []
        bus.subscribe("*", events.append)
        manager = MemoryManager(
            SQLiteMemoryProvider(self.path),
            event_bus=bus,
            default_source="voice",
            default_source_provider="openai",
            default_created_by="user",
        )

        stored = manager.store(
            "relationship.아야.location",
            "오사카",
            MemoryType.LONG_TERM,
            confidence=0.98,
        )
        updated = manager.store(
            "relationship.아야.location",
            "도쿄",
            MemoryType.LONG_TERM,
            confidence=0.9,
        )
        manager.retrieve("도쿄")
        manager.delete("relationship.아야.location", MemoryType.LONG_TERM)

        self.assertEqual(
            [event.event_type for event in events],
            ["MemoryStored", "MemoryUpdated", "MemoryRetrieved", "MemoryDeleted"],
        )
        self.assertEqual(stored.source, "voice")
        self.assertEqual(stored.source_provider, "openai")
        self.assertEqual(stored.created_by, "user")
        self.assertEqual(stored.confidence, 0.98)
        self.assertEqual(updated.id, stored.id)
        event_text = " ".join(event.to_json() for event in events)
        self.assertNotIn("오사카", event_text)
        self.assertNotIn("도쿄", event_text)
        self.assertIn("key_fingerprint", events[0].payload)

    def test_preference_change_event_includes_provenance_and_timestamps(self):
        bus = InMemoryEventBus()
        events = []
        bus.subscribe("*", events.append)
        manager = MemoryManager(
            SQLiteMemoryProvider(self.path),
            event_bus=bus,
            default_source="voice",
            default_source_provider="openai",
        )

        saved = manager.store(
            "preference.weather.default_location",
            "강릉",
            MemoryType.PREFERENCE,
            confidence=1.0,
        )

        self.assertEqual(
            [event.event_type for event in events],
            ["MemoryStored", "PreferenceChanged"],
        )
        preference_event = events[1]
        self.assertEqual(preference_event.payload["source"], "voice")
        self.assertEqual(preference_event.payload["provider"], "openai")
        self.assertEqual(preference_event.payload["confidence"], 1.0)
        self.assertEqual(preference_event.payload["created_at"], saved.created_at)
        self.assertEqual(preference_event.payload["updated_at"], saved.updated_at)
        self.assertNotIn("강릉", preference_event.to_json())
        self.assertEqual(saved.to_dict()["provider"], "openai")

    def test_sqlite_provider_migrates_source_and_ttl_columns(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(key, memory_type, scope, session_id)
            )
            """
        )
        connection.commit()
        connection.close()

        provider = SQLiteMemoryProvider(self.path)
        manager = MemoryManager(provider)
        saved = manager.store(
            "user.location",
            "강릉",
            MemoryType.LONG_TERM,
            source_provider="openai",
            created_by="user",
        )

        self.assertEqual(saved.source_provider, "openai")
        self.assertEqual(saved.created_by, "user")

    def test_store_policy_rejects_ephemeral_meal(self):
        decision = MemoryStorePolicy().decide("오늘 점심은 김치찌개 먹었어.")

        self.assertFalse(decision.should_store)
        self.assertEqual(decision.reason, "ephemeral_or_unclassified")

    def test_store_policy_classifies_preference_and_relationship(self):
        policy = MemoryStorePolicy()

        preference = policy.decide("앞으로 기본 날씨는 강릉으로 해줘.")
        relationship = policy.decide("아야는 오사카에 살아.")

        self.assertTrue(preference.should_store)
        self.assertEqual(preference.memory_type, MemoryType.PREFERENCE)
        self.assertEqual(preference.key, "preference.weather.default_location")
        self.assertEqual(preference.value, "강릉")
        self.assertTrue(relationship.should_store)
        self.assertEqual(relationship.memory_type, MemoryType.LONG_TERM)
        self.assertEqual(relationship.key, "relationship.아야.location")

    def test_store_policy_classifies_runtime_preferences_and_user_location(self):
        policy = MemoryStorePolicy()

        speed = policy.decide("TTS 속도는 1.25로 해줘.")
        voice = policy.decide("기본 목소리는 Onyx로 해줘.")
        location = policy.decide("나는 강릉에 살아.")

        self.assertEqual(speed.key, "preference.tts.speed")
        self.assertEqual(speed.value, "1.25")
        self.assertEqual(voice.key, "preference.tts.voice")
        self.assertEqual(voice.value, "onyx")
        self.assertEqual(location.key, "user.location")
        self.assertEqual(location.value, "강릉")

    def test_store_policy_accepts_observed_preference_and_fact_variants(self):
        policy = MemoryStorePolicy()

        short_preference = policy.decide("앞으로 기본 날씨를 강릉으로 해.")
        stt_preference = policy.decide("앞으로 기본 날씨를 강릉으로 해로.")
        relationship = policy.decide("아야는 오사카에 산다.")

        self.assertTrue(short_preference.should_store)
        self.assertEqual(short_preference.value, "강릉")
        self.assertTrue(stt_preference.should_store)
        self.assertEqual(stt_preference.value, "강릉")
        self.assertTrue(relationship.should_store)
        self.assertEqual(relationship.value, "오사카")

    def test_weather_preference_save_message_is_user_facing(self):
        entry = MemoryEntry(
            id="memory-weather-location",
            key="preference.weather.default_location",
            value="강릉",
            category="preference",
        )

        self.assertEqual(format_saved_message(entry), "기본 날씨 지역을 강릉으로 설정했습니다.")

    def test_successful_ability_execution_applies_store_policy(self):
        manager = MemoryManager(SQLiteMemoryProvider(self.path))
        request = SimpleNamespace(
            input_data={"text": "아야는 오사카에 살아."},
        )
        result = SimpleNamespace(success=True)

        saved = manager.observe_execution(request, result)

        self.assertEqual(saved.key, "relationship.아야.location")
        self.assertEqual(
            manager.retrieve("오사카").get("relationship.아야.location"),
            "오사카",
        )

    def test_planner_applies_retrieved_weather_preference(self):
        manager = MemoryManager(SQLiteMemoryProvider(self.path))
        manager.apply_store_policy("앞으로 기본 날씨는 강릉으로 해줘.")
        plan = ExecutionPlan(
            raw_text="내일 날씨 알려줘",
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="weather",
                    action="query",
                    input_data={"text": "내일 날씨 알려줘"},
                ),
            ),
        )

        enriched = apply_memory_context(plan, manager.retrieve(plan.raw_text))

        self.assertEqual(
            enriched.steps[0].input_data["_memory_default_location"],
            "강릉",
        )
        self.assertNotIn("_memory_default_location", plan.steps[0].input_data)

    def test_store_policy_becomes_explicit_memory_plan(self):
        manager = MemoryManager(SQLiteMemoryProvider(self.path))
        dispatcher = RuntimeToolDispatcher(
            PolicyRegistry(),
            memory_manager=manager,
        )

        plan = dispatcher.create_plan("앞으로 기본 날씨는 강릉으로 해줘.")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "memory")
        self.assertEqual(
            plan.steps[0].input_data["key"],
            "preference.weather.default_location",
        )
        self.assertEqual(plan.steps[0].input_data["value"], "강릉")


class PolicyRegistry:
    def exists(self, name):
        return name == "memory"

    def get(self, name):
        return None

    def list(self):
        return []


if __name__ == "__main__":
    unittest.main()
