import json
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

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

    def test_timeline_is_compact_and_chronological(self):
        journal = ExecutionJournal()
        journal.record(
            "RT-VIEW",
            JournalPhase.PLAN,
            "PLAN_CREATED",
            "CREATED",
            timestamp="2026-07-27T14:00:12.100",
        )
        journal.record(
            "RT-VIEW",
            JournalPhase.VALIDATION,
            "PLAN_VALIDATED",
            "VALID",
            timestamp="2026-07-27T14:00:13.200",
        )

        timeline = journal.timeline("RT-VIEW")

        self.assertIn("14:00:12.100  PLAN", timeline)
        self.assertIn("14:00:13.200  VALIDATION", timeline)
        self.assertLess(timeline.index("PLAN_CREATED"), timeline.index("PLAN_VALIDATED"))

    def test_tree_groups_operations_under_phases(self):
        journal = ExecutionJournal()
        journal.record(
            "RT-TREE",
            JournalPhase.EXECUTION,
            "STEP_COMPLETED",
            "SUCCESS",
            {"capability": "calendar", "operation": "create"},
        )
        journal.record(
            "RT-TREE",
            JournalPhase.PERMISSION,
            "CONFIRMATION_REQUESTED",
            "PENDING",
            {"capability": "mail", "operation": "send"},
        )

        tree = journal.tree("RT-TREE")

        self.assertIn("|-- EXECUTION", tree)
        self.assertIn("calendar.create [SUCCESS]", tree)
        self.assertIn("`-- PERMISSION", tree)
        self.assertIn("mail.send [PENDING]", tree)

    def test_explain_why_renders_permission_causal_path(self):
        journal = ExecutionJournal()
        journal.record(
            "RT-WHY-VIEW",
            JournalPhase.DISCOVERY,
            "CAPABILITY_SELECTED",
            "SELECTED",
            {"capability": "mail", "operation": "send", "reason": "BEST_POLICY_SCORE"},
        )
        journal.record(
            "RT-WHY-VIEW",
            JournalPhase.PERMISSION,
            "CONFIRMATION_REQUESTED",
            "PENDING",
            {"capability": "mail", "operation": "send"},
        )

        rendered = journal.explain_why("RT-WHY-VIEW")

        self.assertIn("CAPABILITY_SELECTED (mail.send)", rendered)
        self.assertIn("CONFIRMATION_REQUESTED (mail.send)", rendered)

    def test_semantic_search_finds_recent_operational_categories(self):
        journal = ExecutionJournal()
        journal.record(
            "RT-CALENDAR",
            JournalPhase.EXECUTION,
            "STEP_COMPLETED",
            "SUCCESS",
            {"capability": "calendar", "operation": "create"},
            timestamp="2026-07-27T10:00:00",
        )
        journal.record(
            "RT-MAIL",
            JournalPhase.EXECUTION,
            "STEP_FAILED",
            "FAILED",
            {"capability": "mail", "operation": "send"},
            timestamp="2026-07-27T11:00:00",
        )
        journal.record(
            "RT-RETRY",
            JournalPhase.RECOVERY,
            "RECOVERY_DECIDED",
            "RETRYING",
            {"recovery_strategy": "BACKOFF", "retry_count": 1},
            timestamp="2026-07-27T12:00:00",
        )
        journal.record(
            "RT-AUTH",
            JournalPhase.RECOVERY,
            "TaskPaused",
            "PAUSED",
            {"reason": "recovery_reauth"},
            timestamp="2026-07-27T13:00:00",
        )

        self.assertEqual(journal.search("최근 실패").task_ids, ("RT-MAIL",))
        self.assertEqual(journal.search("최근 Retry").task_ids, ("RT-RETRY",))
        self.assertEqual(journal.search("최근 Calendar").task_ids, ("RT-CALENDAR",))
        self.assertEqual(journal.search("최근 Gmail").task_ids, ("RT-MAIL",))
        self.assertEqual(journal.search("최근 OAuth").task_ids, ("RT-AUTH",))
        self.assertEqual(journal.search("최근 Pause").task_ids, ("RT-AUTH",))

    def test_export_writes_json_markdown_and_html_without_sensitive_data(self):
        journal = ExecutionJournal()
        journal.record(
            "RT-EXPORT",
            JournalPhase.EXECUTION,
            "MAIL_SENT",
            "SUCCESS",
            {
                "capability": "mail",
                "operation": "send",
                "recipient": "private@example.com",
                "body": "private body",
            },
        )

        contents = []
        with patch.object(Path, "mkdir"), patch.object(Path, "write_text") as write_text:
            for name in ("journal.json", "journal.md", "journal.html"):
                journal.export(Path("output") / name)
                contents.append(write_text.call_args.args[0])

        self.assertTrue(all("RT-EXPORT" in content for content in contents))
        self.assertTrue(all("private@example.com" not in content for content in contents))
        self.assertTrue(all("private body" not in content for content in contents))
        self.assertIn("# Jarvis Execution Journal", contents[1])
        self.assertIn("<!doctype html>", contents[2])

    def test_export_rejects_unknown_format(self):
        journal = ExecutionJournal()

        with self.assertRaisesRegex(ValueError, "JOURNAL_EXPORT_FORMAT_UNSUPPORTED"):
            journal.export("journal.txt")


if __name__ == "__main__":
    unittest.main()
