from pathlib import Path
from types import SimpleNamespace
import unittest

from jarvis.memory import (
    MemoryManager,
    MemoryStorePolicy,
    MemoryType,
    SQLiteMemoryProvider,
)
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
