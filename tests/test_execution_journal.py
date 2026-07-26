import json
import unittest
from dataclasses import replace
from datetime import date, timedelta

from jarvis.abilities.native.calendar import CalendarEvent
from jarvis.core.events import BaseEvent, InMemoryEventBus
from jarvis.runtime import ExecutionJournal, JournalPhase
from jarvis.runtime.execution_journal import JournalEntry
from tests.test_workspace_integration import create_dispatcher


class TestExecutionJournalSprint186(unittest.TestCase):
    def test_entries_are_ordered_and_fingerprint_chained(self):
        journal = ExecutionJournal(clock=lambda: "2026-07-27T10:00:00.000")

        first = journal.record("RT-1", JournalPhase.GOAL, "GOAL_ACCEPTED", "ACCEPTED")
        second = journal.record(
            "RT-1",
            JournalPhase.PLAN,
            "PLAN_CREATED",
            "CREATED",
            {"plan_id": "P-1", "step_count": 2},
        )

        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(second.previous_fingerprint, first.fingerprint)
        self.assertTrue(journal.replay("RT-1").valid)

    def test_sensitive_metadata_is_never_stored(self):
        journal = ExecutionJournal()

        entry = journal.record(
            "RT-PII",
            JournalPhase.EXECUTION,
            "MAIL_SENT",
            "SUCCESS",
            {
                "operation": "send",
                "provider": "google",
                "email": "person@example.com",
                "recipient": "person@example.com",
                "subject": "private subject",
                "body": "private body",
                "prompt": "raw user input",
                "reason": "person@example.com",
            },
        )

        self.assertEqual(entry.metadata, {"operation": "send", "provider": "google"})
        encoded = json.dumps(entry.to_dict(), ensure_ascii=False)
        self.assertNotIn("person@example.com", encoded)
        self.assertNotIn("private", encoded)
        self.assertNotIn("raw user", encoded)

    def test_event_bus_projects_runtime_transition(self):
        bus = InMemoryEventBus()
        journal = ExecutionJournal()
        bus.subscribe("*", journal.handle)

        bus.publish(
            BaseEvent(
                event_type="TaskStateChanged",
                aggregate_type="RuntimeTask",
                aggregate_id="RT-EVENT",
                payload={
                    "task_id": "RT-EVENT",
                    "transition_id": 2,
                    "previous_state": "RUNNING",
                    "new_state": "WAIT_CONFIRM",
                    "transition_reason": "permission",
                    "transition_source": "SYSTEM",
                    "checkpoint_fingerprint": "a" * 64,
                    "mail_body": "must not persist",
                },
            )
        )

        entry = journal.store.entries("RT-EVENT")[0]
        self.assertEqual(entry.phase, JournalPhase.PERMISSION)
        self.assertEqual(entry.status, "WAIT_CONFIRM")
        self.assertNotIn("mail_body", entry.metadata)

    def test_serialization_restore_preserves_replay(self):
        journal = ExecutionJournal()
        journal.record("RT-SER", JournalPhase.GOAL, "GOAL_ACCEPTED", "ACCEPTED")
        journal.record(
            "RT-SER",
            JournalPhase.RESULT,
            "TASK_RESULT",
            "SUCCESS",
            {"status": "SUCCESS", "duration_ms": 12},
        )

        restored = ExecutionJournal.from_json(journal.to_json())

        self.assertTrue(restored.replay("RT-SER").valid)
        self.assertEqual(
            [entry.to_dict() for entry in restored.store.entries("RT-SER")],
            [entry.to_dict() for entry in journal.store.entries("RT-SER")],
        )

    def test_replay_detects_tampered_entry(self):
        journal = ExecutionJournal()
        journal.record("RT-TAMPER", JournalPhase.GOAL, "GOAL_ACCEPTED", "ACCEPTED")
        original = journal.record(
            "RT-TAMPER",
            JournalPhase.RESULT,
            "TASK_RESULT",
            "SUCCESS",
            {"status": "SUCCESS"},
        )
        journal.store._entries["RT-TAMPER"][1] = replace(original, status="FAILED")

        replay = journal.replay("RT-TAMPER")

        self.assertFalse(replay.valid)
        self.assertEqual(replay.errors, ("FINGERPRINT:2",))

    def test_explain_uses_recorded_reasons_without_goal_text(self):
        journal = ExecutionJournal()
        journal.record("RT-WHY", JournalPhase.GOAL, "GOAL_ACCEPTED", "ACCEPTED")
        journal.record(
            "RT-WHY",
            JournalPhase.DISCOVERY,
            "CAPABILITY_SELECTED",
            "SELECTED",
            {
                "selected_implementation": "google_mail",
                "availability": "ONLINE",
                "reliability_score": 0.98,
                "reason": "BEST_POLICY_SCORE",
            },
        )
        journal.record(
            "RT-WHY",
            JournalPhase.RESULT,
            "TASK_RESULT",
            "SUCCESS",
            {"status": "SUCCESS"},
        )

        explanation = journal.explain("RT-WHY")

        self.assertEqual(explanation.status, "SUCCESS")
        self.assertIn("DISCOVERY:CAPABILITY_SELECTED:BEST_POLICY_SCORE", explanation.reasons)
        self.assertIn("DISCOVERY:selected:google_mail", explanation.reasons)

    def test_query_filters_task_history(self):
        journal = ExecutionJournal()
        journal.record("RT-A", JournalPhase.RESULT, "TASK_RESULT", "FAILED")
        journal.record("RT-B", JournalPhase.RESULT, "TASK_RESULT", "SUCCESS")

        failed = journal.query(phase=JournalPhase.RESULT, status="FAILED")

        self.assertEqual([entry.task_id for entry in failed], ["RT-A"])

    def test_artifacts_store_references_not_payloads(self):
        journal = ExecutionJournal()
        journal.record("RT-ART", JournalPhase.GOAL, "GOAL_ACCEPTED", "ACCEPTED")

        artifact = journal.add_artifact(
            "RT-ART",
            "mail_draft",
            "f" * 64,
            verified=True,
            size=42,
            media_type="message/rfc822",
        )

        self.assertTrue(artifact.verified)
        self.assertFalse(hasattr(artifact, "payload"))
        self.assertNotIn("body", journal.to_json("RT-ART").lower())

    def test_dispatcher_runtime_records_full_execution_path(self):
        event_date = (date.today() + timedelta(days=1)).isoformat()
        dispatcher, _, _ = create_dispatcher(
            events=[
                CalendarEvent(
                    id="event-journal",
                    title="Journal test",
                    date=event_date,
                    time="15:00",
                )
            ]
        )

        result = dispatcher.execute_plan_text(
            "\uc544\uc57c\uc5d0\uac8c \ub0b4\uc77c \uc624\ud6c4 3\uc2dc "
            "\uc77c\uc815 \uba54\uc77c\ub85c \ubcf4\ub0b4\uc918"
        )
        task_id = result.task.id
        entries = dispatcher.execution_journal.store.entries(task_id)
        phases = {entry.phase for entry in entries}

        self.assertEqual(result.error, "confirm_required")
        self.assertTrue(
            {
                JournalPhase.GOAL,
                JournalPhase.PLAN,
                JournalPhase.DISCOVERY,
                JournalPhase.VALIDATION,
                JournalPhase.OPTIMIZATION,
                JournalPhase.EXECUTION,
                JournalPhase.VERIFICATION,
                JournalPhase.PERMISSION,
                JournalPhase.RESULT,
            }.issubset(phases)
        )
        self.assertTrue(dispatcher.execution_journal.replay(task_id).valid)
        serialized = dispatcher.execution_journal.to_json(task_id)
        self.assertNotIn("@", serialized)
        self.assertNotIn("\uba54\uc77c\ub85c \ubcf4\ub0b4\uc918", serialized)

    def test_from_json_rejects_task_mismatch(self):
        entry = JournalEntry(
            id="JE-1",
            timestamp="2026-07-27T10:00:00",
            task_id="RT-WRONG",
            sequence=1,
            phase=JournalPhase.GOAL,
            event="GOAL_ACCEPTED",
            status="ACCEPTED",
            fingerprint="x",
        )
        payload = {
            "schema_version": 1,
            "tasks": {"RT-EXPECTED": [entry.to_dict()]},
            "artifacts": {},
        }

        with self.assertRaisesRegex(ValueError, "JOURNAL_TASK_ID_MISMATCH"):
            ExecutionJournal.from_json(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
