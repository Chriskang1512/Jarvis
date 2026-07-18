import os
import time
import unittest
from datetime import datetime

from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.core.contacts import ContactRepository, InMemoryContactStorage
from jarvis.core.events import (
    BaseEvent,
    DeadLetterRecorder,
    EventContext,
    EventHistoryHandler,
    EventRecorder,
    InMemoryEventBus,
    ReplayOptions,
    ReminderScheduleHandler,
    RetryPolicy,
    replay_events,
)
from jarvis.core.events.exceptions import TemporaryEventHandlerError
from jarvis.native.reminder import ReminderEngine, ReminderQueue
from jarvis.native.reminder.reminder import REMINDER_PENDING


class TestCoreEventBusFoundation(unittest.TestCase):
    """Test Sprint 15 Core EventBus foundation."""

    def test_base_event_serializes_for_replay(self):
        event = BaseEvent(
            event_type="ContactUpdated",
            aggregate_type="contact",
            aggregate_id="person_aya",
            revision=2,
            trace_id="trace-1",
            correlation_id="corr-1",
            payload={"changed_fields": ["birthday"]},
        )

        loaded = BaseEvent.from_json(event.to_json())

        self.assertEqual(loaded.version, 1)
        self.assertEqual(loaded.event_type, "ContactUpdated")
        self.assertEqual(loaded.aggregate_id, "person_aya")
        self.assertEqual(loaded.correlation_id, "corr-1")
        self.assertEqual(loaded.payload["changed_fields"], ["birthday"])

    def test_retry_policy_succeeds_on_second_attempt_without_dead_letter(self):
        dead_letters = DeadLetterRecorder(path=os.path.join("tmp", "tests", "retry_success_dead_letters.jsonl"))
        bus = InMemoryEventBus(dead_letter_recorder=dead_letters)
        calls = []

        def flaky(_event):
            calls.append("call")
            if len(calls) == 1:
                raise TemporaryEventHandlerError("temporary")

        bus.subscribe(
            "ContactUpdated",
            flaky,
            retry_policy=RetryPolicy(max_attempts=2, retry_delay_ms=0, backoff_strategy="fixed"),
        )

        result = bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))

        self.assertTrue(result.success)
        self.assertEqual(result.handlers_retried, 1)
        self.assertEqual(result.handler_results[0].attempts, 2)
        self.assertEqual(calls, ["call", "call"])
        self.assertEqual(dead_letters.list_dead_letters(), [])
        self.assertEqual(bus.metrics.event_retried, 1)

    def test_handler_timeout_records_failure_contract(self):
        dead_letters = DeadLetterRecorder(path=os.path.join("tmp", "tests", "timeout_dead_letters.jsonl"))
        bus = InMemoryEventBus(dead_letter_recorder=dead_letters)

        def slow(_event):
            time.sleep(0.002)

        bus.subscribe("ContactUpdated", slow, handler_timeout_ms=1)

        result = bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))

        self.assertFalse(result.success)
        self.assertEqual(result.handler_results[0].error_type, "EventHandlerTimeout")
        self.assertEqual(len(dead_letters.list_dead_letters()), 1)

    def test_validation_error_does_not_retry_and_creates_dead_letter(self):
        path = os.path.join("tmp", "tests", "validation_dead_letters.jsonl")
        if os.path.exists(path):
            os.remove(path)
        dead_letters = DeadLetterRecorder(path=path)
        bus = InMemoryEventBus(dead_letter_recorder=dead_letters)
        calls = []

        def invalid(_event):
            calls.append("call")
            raise ValueError("bad payload")

        bus.subscribe(
            "ContactUpdated",
            invalid,
            retry_policy=RetryPolicy(max_attempts=3, retry_delay_ms=0, backoff_strategy="fixed"),
        )

        result = bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))

        self.assertFalse(result.success)
        self.assertEqual(calls, ["call"])
        self.assertEqual(result.handler_results[0].attempts, 1)
        self.assertEqual(result.handler_results[0].error_type, "ValueError")
        self.assertEqual(result.dead_letters_created, 1)
        self.assertEqual(len(dead_letters.list_dead_letters(status="PENDING")), 1)
        os.remove(path)

    def test_handler_failure_does_not_stop_other_handlers(self):
        bus = InMemoryEventBus()
        calls = []

        def broken(_event):
            calls.append("broken")
            raise RuntimeError("handler boom")

        def healthy(_event):
            calls.append("healthy")

        bus.subscribe("ContactUpdated", broken)
        bus.subscribe("ContactUpdated", healthy)

        result = bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))

        self.assertFalse(result.success)
        self.assertEqual(calls, ["broken", "healthy"])
        self.assertEqual(bus.metrics.event_failed, 1)
        self.assertEqual(bus.metrics.event_handled, 1)

    def test_handlers_run_by_priority_then_subscription_order(self):
        bus = InMemoryEventBus()
        calls = []

        bus.subscribe("ContactUpdated", lambda _event: calls.append("low"), priority=10)
        bus.subscribe("ContactUpdated", lambda _event: calls.append("high-first"), priority=100)
        bus.subscribe("ContactUpdated", lambda _event: calls.append("high-second"), priority=100)
        bus.subscribe("ContactUpdated", lambda _event: calls.append("middle"), priority=50)

        bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))

        self.assertEqual(calls, ["high-first", "high-second", "middle", "low"])

    def test_event_context_fills_trace_correlation_and_metadata(self):
        bus = InMemoryEventBus()
        seen = []
        bus.subscribe("ContactUpdated", lambda event: seen.append(event), priority=100)

        bus.publish(
            BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"),
            context=EventContext(
                trace_id="trace-1",
                correlation_id="corr-1",
                causation_id="cause-1",
                session_id="session-1",
                task_id="RT-1234",
                permission_scope="safe",
            ),
        )

        self.assertEqual(seen[0].trace_id, "trace-1")
        self.assertEqual(seen[0].correlation_id, "corr-1")
        self.assertEqual(seen[0].causation_id, "cause-1")
        self.assertEqual(seen[0].metadata["session_id"], "session-1")
        self.assertEqual(seen[0].metadata["task_id"], "RT-1234")
        self.assertEqual(seen[0].metadata["permission_scope"], "safe")

    def test_duplicate_event_is_idempotent_per_handler(self):
        bus = InMemoryEventBus()
        calls = []
        bus.subscribe("ContactUpdated", lambda event: calls.append(event.event_id))
        event = BaseEvent(event_id="EV-fixed", event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya")

        first = bus.publish(event)
        second = bus.publish(event)

        self.assertEqual(len(first.handler_results), 1)
        self.assertEqual(len(second.handler_results), 0)
        self.assertEqual(calls, ["EV-fixed"])
        self.assertEqual(bus.metrics.duplicate_skipped, 1)

    def test_idempotency_key_blocks_business_duplicate_with_different_event_id(self):
        bus = InMemoryEventBus()
        calls = []
        bus.subscribe("CalendarCreated", lambda event: calls.append(event.event_id))

        first = BaseEvent(
            event_type="CalendarCreated",
            aggregate_type="calendar",
            aggregate_id="mock-3",
            idempotency_key="calendar.created:mock-3:r1",
        )
        second = BaseEvent(
            event_type="CalendarCreated",
            aggregate_type="calendar",
            aggregate_id="mock-3",
            idempotency_key="calendar.created:mock-3:r1",
        )

        first_result = bus.publish(first)
        second_result = bus.publish(second)

        self.assertTrue(first_result.success)
        self.assertTrue(second_result.duplicate)
        self.assertEqual(calls, [first.event_id])

    def test_contact_update_publishes_event_to_history_handler(self):
        bus = InMemoryEventBus()
        history = EventHistoryHandler()
        bus.subscribe("ContactUpdated", history)
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False, event_bus=bus)

        contact = repository.create("Aya")
        repository.update(contact.id, birthday="1991-02-28")

        self.assertEqual(len(history.events), 1)
        self.assertEqual(history.events[0].event_type, "ContactUpdated")
        self.assertEqual(history.events[0].aggregate_type, "contact")
        self.assertEqual(history.events[0].aggregate_id, contact.id)
        self.assertEqual(history.events[0].payload["changed_fields"], ["birthday"])

    def test_calendar_created_event_schedules_reminder(self):
        engine = ReminderEngine(queue=ReminderQueue())
        bus = InMemoryEventBus()
        bus.subscribe("CalendarCreated", ReminderScheduleHandler(engine))
        provider = MockCalendarProvider(events=[])
        ability = CalendarAbility(
            provider=provider,
            event_bus=bus,
            now_provider=lambda: datetime(2026, 7, 9, 18, 0, 0),
        )

        result = ability.execute(
            {
                "action": "create",
                "date": "2026-07-10",
                "time": "15:00",
                "title": "meeting",
                "raw_text": "meeting 30",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        reminders = engine.list(state=REMINDER_PENDING)
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].title, "meeting")
        self.assertEqual(reminders[0].calendar_id, result.data.events[0].id)
        self.assertEqual(reminders[0].trigger_time, "2026-07-10T14:30:00")

    def test_calendar_to_reminder_follow_up_event_sets_causation_id(self):
        engine = ReminderEngine(queue=ReminderQueue())
        bus = InMemoryEventBus()
        reminder_events = []
        bus.subscribe("CalendarCreated", ReminderScheduleHandler(engine, event_bus=bus))
        bus.subscribe("ReminderCreated", lambda event: reminder_events.append(event))
        event = BaseEvent(
            event_id="EV-calendar-parent",
            event_type="CalendarCreated",
            aggregate_type="calendar",
            aggregate_id="mock-1",
            correlation_id="corr-1",
            payload={
                "events": [
                    {
                        "id": "mock-1",
                        "title": "meeting",
                        "date": "2026-07-10",
                        "time": "15:00",
                    }
                ],
                "remind_before": 30,
            },
        )

        bus.publish(event)

        self.assertEqual(len(reminder_events), 1)
        self.assertEqual(reminder_events[0].event_type, "ReminderCreated")
        self.assertEqual(reminder_events[0].causation_id, "EV-calendar-parent")
        self.assertEqual(reminder_events[0].correlation_id, "corr-1")

    def test_event_recorder_writes_jsonl(self):
        path = os.path.join("tmp", "tests", "event_recorder_test.jsonl")

        if os.path.exists(path):
            os.remove(path)

        recorder = EventRecorder(path=path)
        bus = InMemoryEventBus(recorder=recorder)
        event = BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya")

        bus.publish(event)

        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        self.assertIn("ContactUpdated", content)
        self.assertIn(event.event_id, content)

        os.remove(path)

    def test_dead_letter_recorder_stores_handler_failure(self):
        path = os.path.join("tmp", "tests", "event_dead_letter_test.jsonl")

        if os.path.exists(path):
            os.remove(path)

        dead_letters = DeadLetterRecorder(path=path)
        bus = InMemoryEventBus(dead_letter_recorder=dead_letters)

        def broken(_event):
            raise RuntimeError("sync failed")

        bus.subscribe("ContactUpdated", broken)
        bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))

        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        self.assertIn("DeadLetter", content)
        self.assertIn("sync failed", content)
        self.assertIn("broken", content)

        os.remove(path)

    def test_dead_letter_retry_and_resolve_lifecycle(self):
        path = os.path.join("tmp", "tests", "dead_letter_lifecycle.jsonl")
        if os.path.exists(path):
            os.remove(path)
        dead_letters = DeadLetterRecorder(path=path)
        failing_bus = InMemoryEventBus(dead_letter_recorder=dead_letters)
        failing_bus.subscribe("ContactUpdated", lambda _event: (_ for _ in ()).throw(RuntimeError("failed once")))

        failing_bus.publish(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))
        dead_letter = dead_letters.list_dead_letters()[0]

        replay_bus = InMemoryEventBus()
        calls = []
        replay_bus.subscribe("ContactUpdated", lambda event: calls.append(event.aggregate_id))
        retry_result = dead_letters.retry_dead_letter(dead_letter.dead_letter_id, replay_bus, bypass_idempotency=True)

        self.assertTrue(retry_result.success)
        self.assertEqual(calls, ["person_aya"])
        self.assertEqual(dead_letters.get_dead_letter(dead_letter.dead_letter_id).status, "RESOLVED")
        discarded = dead_letters.discard_dead_letter(dead_letter.dead_letter_id, note="cleanup")
        self.assertEqual(discarded.status, "DISCARDED")
        os.remove(path)

    def test_replay_events_republishes_recorded_jsonl(self):
        path = os.path.join("tmp", "tests", "event_replay_test.jsonl")

        if os.path.exists(path):
            os.remove(path)

        recorder = EventRecorder(path=path)
        recorded_event = BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya")
        recorder.record(recorded_event)
        replay_bus = InMemoryEventBus()
        calls = []
        replay_bus.subscribe("ContactUpdated", lambda event: calls.append(event.event_id))

        preview = replay_events(path, replay_bus)
        results = replay_events(path, replay_bus, dry_run=False)

        self.assertTrue(preview.dry_run)
        self.assertEqual(preview.events, 1)
        self.assertEqual(preview.would_execute, 1)
        self.assertEqual(len(results.publish_results), 1)
        self.assertEqual(calls, [recorded_event.event_id])

        os.remove(path)

    def test_replay_respects_idempotency_and_bypass_option(self):
        path = os.path.join("tmp", "tests", "event_replay_idempotency_test.jsonl")
        if os.path.exists(path):
            os.remove(path)

        recorder = EventRecorder(path=path)
        recorded_event = BaseEvent(
            event_type="CalendarCreated",
            aggregate_type="calendar",
            aggregate_id="mock-3",
            idempotency_key="calendar.created:mock-3:r1",
        )
        recorder.record(recorded_event)
        replay_bus = InMemoryEventBus()
        calls = []
        replay_bus.subscribe("CalendarCreated", lambda event: calls.append(event.event_id))

        replay_events(path, replay_bus, dry_run=False)
        duplicate = replay_events(path, replay_bus, dry_run=False)
        bypassed = replay_events(
            path,
            replay_bus,
            options=ReplayOptions(dry_run=False, bypass_idempotency=True, preserve_event_id=False),
        )

        self.assertEqual(len(calls), 2)
        self.assertTrue(duplicate.publish_results[0].duplicate)
        self.assertFalse(bypassed.publish_results[0].duplicate)
        os.remove(path)

    def test_replay_can_filter_handler_names(self):
        path = os.path.join("tmp", "tests", "event_replay_handler_filter_test.jsonl")
        if os.path.exists(path):
            os.remove(path)

        recorder = EventRecorder(path=path)
        recorder.record(BaseEvent(event_type="ContactUpdated", aggregate_type="contact", aggregate_id="person_aya"))
        replay_bus = InMemoryEventBus()
        calls = []

        def first(_event):
            calls.append("first")

        def second(_event):
            calls.append("second")

        replay_bus.subscribe("ContactUpdated", first)
        replay_bus.subscribe("ContactUpdated", second)

        preview = replay_events(path, replay_bus, options=ReplayOptions(dry_run=True, handler_names=("first",)))
        replay_events(path, replay_bus, options=ReplayOptions(dry_run=False, handler_names=("first",)))

        self.assertEqual(preview.handlers, 1)
        self.assertEqual(calls, ["first"])
        os.remove(path)

    def test_event_bus_metrics_console_and_flush_close(self):
        bus = InMemoryEventBus(recorder=EventRecorder(enabled=False), dead_letter_recorder=DeadLetterRecorder(enabled=False))
        lines = bus.metrics.to_console_lines()

        self.assertIn("Event Bus", lines[0])
        self.assertTrue(bus.flush())
        self.assertTrue(bus.close())


if __name__ == "__main__":
    unittest.main()
