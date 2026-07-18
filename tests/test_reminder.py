import unittest
from datetime import datetime, timedelta

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility
from jarvis.abilities.native.calendar import MockCalendarProvider
from jarvis.abilities.native.reminder import ReminderAbility, ReminderIntentParser
from jarvis.native.reminder import ReminderEngine, ReminderQueue
from jarvis.native.reminder.engine import reminder_notification_text
from jarvis.native.reminder.reminder import REMINDER_CANCELLED, REMINDER_COMPLETED, REMINDER_PENDING
from jarvis.tools import ToolDispatcher, ToolRequest, ToolRegistry, create_default_tool_registry


class TestReminderSprint4(unittest.TestCase):
    """Test Sprint 4 Reminder and Scheduler foundation."""

    def test_reminder_parser_extracts_before_minutes(self):
        """Check remind-before phrases."""
        parser = ReminderIntentParser()

        self.assertEqual(parser.parse("내일 오후 3시에 아야 만나기 30분 전 알림 등록해").remind_before, 30)
        self.assertEqual(parser.parse("내일 오후 3시에 아야 만나기 10분 전 알림 등록해").remind_before, 10)
        self.assertEqual(parser.parse("내일 오후 3시에 아야 만나기 1시간 전 알림 등록해").remind_before, 60)

    def test_reminder_parser_extracts_datetime(self):
        """Check simple date/time parsing."""
        query = ReminderIntentParser().parse("내일 오후 3시에 아야 만나기 30분 전 알림 등록해")

        self.assertEqual(query.datetime[-8:], "15:00:00")
        self.assertEqual(query.title, "아야 만나기")

    def test_reminder_parser_extracts_relative_alarm(self):
        """Check direct relative alarm requests create an immediate trigger target."""
        before = datetime.now()

        query = ReminderIntentParser().parse("\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\uac8c \uc54c\ub78c \ub4f1\ub85d\ud574")

        delay_seconds = (datetime.fromisoformat(query.datetime) - before).total_seconds()
        self.assertEqual(query.action, "create")
        self.assertEqual(query.title, "\ubb3c \ub9c8\uc2dc\uae30")
        self.assertEqual(query.remind_before, 0)
        self.assertGreaterEqual(delay_seconds, 55)
        self.assertLessEqual(delay_seconds, 65)

    def test_reminder_parser_cleans_polite_direct_alarm_title(self):
        """Check direct reminder command tails do not leak into title."""
        parser = ReminderIntentParser()

        first = parser.parse("\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\uae30 \uc54c\ub9bc \ub4f1\ub85d\ud574 \uc918")
        second = parser.parse("\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \uc54c\ub824 \uc918")

        self.assertEqual(first.title, "\ubb3c \ub9c8\uc2dc\uae30")
        self.assertEqual(first.remind_before, 0)
        self.assertEqual(second.title, "\ubb3c \ub9c8\uc2dc\uae30")
        self.assertEqual(second.remind_before, 0)

    def test_reminder_parser_cleans_set_alarm_suffix(self):
        """Check alarm setting command suffixes are removed from direct titles."""
        query = ReminderIntentParser().parse("\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\uac8c \uc54c\ub78c \ub9de\ucdb0 \uc918")

        self.assertEqual(query.title, "\ubb3c \ub9c8\uc2dc\uae30")
        self.assertEqual(query.remind_before, 0)

    def test_reminder_parser_names_bare_alarm_and_wake_requests(self):
        """Check direct alarms without an object still get natural titles."""
        parser = ReminderIntentParser()

        wake = parser.parse("1분 뒤에 깨워 줘")
        alarm = parser.parse("1분 뒤에 알람 맞춰 줘")

        self.assertEqual(wake.title, "깨우기")
        self.assertEqual(wake.remind_before, 0)
        self.assertEqual(alarm.title, "알람")
        self.assertEqual(alarm.remind_before, 0)

    def test_reminder_ability_rejects_create_without_time_signal(self):
        """Check ambiguous 'tell me' text does not become a default 09:00 reminder."""
        engine = ReminderEngine(queue=ReminderQueue())
        ability = ReminderAbility(engine=engine)

        result = ability.execute({"text": "\ud560\uc77c \uc54c\ub824\uc918"})

        self.assertFalse(result.success)
        self.assertEqual(result.metadata["error_code"], "time_required")
        self.assertEqual(len(engine.list()), 0)

    def test_queue_enqueue_due_complete_cancel(self):
        """Check queue lifecycle."""
        engine = ReminderEngine(queue=ReminderQueue())
        reminder = engine.create("meeting", datetime.now() + timedelta(minutes=30), remind_before=30)

        self.assertEqual(reminder.state, REMINDER_PENDING)
        self.assertEqual(reminder.status, REMINDER_PENDING)
        self.assertNotEqual(reminder.id, "")
        self.assertNotEqual(reminder.trigger_time, "")
        self.assertNotEqual(reminder.created_at, "")
        self.assertEqual(reminder.updated_at, reminder.created_at)
        self.assertEqual(len(engine.queue.due(datetime.now())), 1)
        completed = engine.queue.complete(reminder.id)
        self.assertEqual(completed.state, REMINDER_COMPLETED)
        self.assertEqual(completed.status, REMINDER_COMPLETED)
        self.assertNotEqual(completed.updated_at, "")

        second = engine.create("other", datetime.now() + timedelta(hours=1), remind_before=30)
        cancelled = engine.queue.cancel(second.id)
        self.assertEqual(cancelled.state, REMINDER_CANCELLED)
        self.assertEqual(cancelled.status, REMINDER_CANCELLED)
        self.assertNotEqual(cancelled.updated_at, "")

    def test_reminder_ability_updates_and_deletes_by_id(self):
        """Check Reminder Ability supports patch update and targeted delete."""
        engine = ReminderEngine(queue=ReminderQueue())
        ability = ReminderAbility(engine=engine)
        reminder = engine.create("water", datetime.now() + timedelta(minutes=30), remind_before=5)

        updated = ability.execute(
            {
                "action": "update",
                "reminder_id": reminder.id,
                "title": "stretch",
            }
        )
        deleted = ability.execute(
            {
                "action": "delete",
                "reminder_id": reminder.id,
            }
        )

        self.assertTrue(updated.success)
        self.assertEqual(updated.data.reminders[0].title, "stretch")
        self.assertEqual(updated.data.reminders[0].remind_before, 5)
        self.assertTrue(deleted.success)
        self.assertEqual(deleted.data.reminders[0].status, REMINDER_CANCELLED)

    def test_reminder_entry_has_calendar_id_trigger_time_status_and_priority(self):
        """Check explicit Reminder ID contract fields."""
        engine = ReminderEngine(queue=ReminderQueue())

        reminder = engine.create(
            "meeting",
            "2026-07-10T15:00:00",
            remind_before=30,
            source="calendar",
            source_id="calendar-123",
            priority="urgent",
        )

        self.assertTrue(reminder.id.startswith("reminder-"))
        self.assertEqual(reminder.calendar_id, "calendar-123")
        self.assertEqual(reminder.trigger_time, "2026-07-10T14:30:00")
        self.assertEqual(reminder.status, REMINDER_PENDING)
        self.assertEqual(reminder.priority, "urgent")
        self.assertEqual(reminder.updated_at, reminder.created_at)

    def test_reminder_parser_seeds_recurrence_and_priority(self):
        """Check recurrence and priority metadata are parsed for Sprint 4.5."""
        parser = ReminderIntentParser()

        self.assertEqual(parser.parse("\ub9e4\uc77c \uc624\uc804 9\uc2dc\uc5d0 \uc57d \uba39\uae30 \uc54c\ub9bc \ub4f1\ub85d\ud574").recurrence, "daily")
        self.assertEqual(parser.parse("\ub9e4\uc8fc \uc6d4\uc694\uc77c \uc624\uc804 9\uc2dc\uc5d0 \ud68c\uc758 \uc54c\ub9bc \ub4f1\ub85d\ud574").recurrence, "weekly")
        self.assertEqual(parser.parse("\ub9e4\ub2ec 1\uc77c \uc624\uc804 9\uc2dc\uc5d0 \uc6d4\uac04 \ubcf4\uace0 \uc54c\ub9bc \ub4f1\ub85d\ud574").recurrence, "monthly")
        self.assertEqual(parser.parse("\ud3c9\uc77c\ub9c8\ub2e4 \uc624\uc804 9\uc2dc\uc5d0 \ucd9c\uadfc \uc54c\ub9bc \ub4f1\ub85d\ud574").recurrence, "weekdays")
        self.assertEqual(parser.parse("\uc8fc\ub9d0\ub9c8\ub2e4 \uc624\uc804 9\uc2dc\uc5d0 \uc6b4\ub3d9 \uc54c\ub9bc \ub4f1\ub85d\ud574").recurrence, "weekends")
        self.assertEqual(parser.parse("\uc544\uc57c \uc0dd\uc77c \uae34\uae09 \uc54c\ub9bc \ub4f1\ub85d\ud574").priority, "urgent")
        self.assertEqual(parser.parse("\ubb3c \ub9c8\uc154 \ub0ae\uc74c \uc54c\ub9bc \ub4f1\ub85d\ud574").priority, "low")

    def test_scheduler_tick_triggers_notification_and_completes(self):
        """Check due reminders trigger notification exactly once."""
        spoken = []
        engine = ReminderEngine(queue=ReminderQueue(), notification_callback=spoken.append)
        reminder = engine.create(
            "아야 만나기",
            datetime.now() + timedelta(minutes=30),
            remind_before=30,
            source="calendar",
            source_id="calendar-1",
        )

        triggered = engine.tick(now=datetime.now())

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].id, reminder.id)
        self.assertEqual(engine.queue.get(reminder.id).state, REMINDER_COMPLETED)
        self.assertEqual(spoken[0], "30분 후 아야와의 약속이 있습니다.")
        self.assertEqual(engine.tick(now=datetime.now()), [])

    def test_scheduler_does_not_trigger_past_event_reminder(self):
        """Check reminders for already-past events are not emitted immediately."""
        spoken = []
        now = datetime(2026, 7, 13, 18, 19, 0)
        engine = ReminderEngine(queue=ReminderQueue(), notification_callback=spoken.append)
        reminder = engine.create(
            "약속",
            "2026-07-13T15:00:00",
            remind_before=30,
            source="calendar",
            source_id="calendar-past",
        )

        triggered = engine.tick(now=now)

        self.assertEqual(triggered, [])
        self.assertEqual(spoken, [])
        self.assertEqual(engine.queue.get(reminder.id).status, REMINDER_PENDING)

    def test_scheduler_triggers_direct_reminder_at_due_time(self):
        """Check direct reminders fire when datetime and trigger time are the same."""
        spoken = []
        due_time = datetime(2026, 7, 13, 21, 20, 6)
        engine = ReminderEngine(queue=ReminderQueue(), notification_callback=spoken.append)
        reminder = engine.create("water", due_time, remind_before=0)

        triggered = engine.tick(now=due_time)

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].id, reminder.id)
        self.assertEqual(engine.queue.get(reminder.id).status, REMINDER_COMPLETED)
        self.assertEqual(len(spoken), 1)
        self.assertIn("water", spoken[0])

    def test_scheduler_triggers_timezone_aware_direct_reminder(self):
        """Check scheduler comparisons handle timezone-aware AI timestamps."""
        spoken = []
        due_time = "2026-07-13T21:36:11+09:00"
        engine = ReminderEngine(queue=ReminderQueue(), notification_callback=spoken.append)
        reminder = engine.create("깨우기", due_time, remind_before=0)

        triggered = engine.tick(now=datetime.fromisoformat(due_time))

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].id, reminder.id)
        self.assertEqual(engine.queue.get(reminder.id).status, REMINDER_COMPLETED)
        self.assertEqual(spoken[0], "깨우기 알림입니다.")

    def test_calendar_reminder_notification_uses_natural_particle(self):
        """Check generic calendar reminders do not say awkward 와의 wording."""
        engine = ReminderEngine(queue=ReminderQueue())
        generic = engine.create("약속", datetime.now() + timedelta(minutes=30), remind_before=30, source="calendar")
        person = engine.create("아야 만나기", datetime.now() + timedelta(minutes=30), remind_before=30, source="calendar")

        self.assertEqual(reminder_notification_text(generic), "30분 후 약속이 있습니다.")
        self.assertEqual(reminder_notification_text(person), "30분 후 아야와의 약속이 있습니다.")

    def test_direct_reminder_notification_uses_alarm_wording(self):
        """Check direct reminders do not use calendar event wording."""
        spoken = []
        engine = ReminderEngine(queue=ReminderQueue(), notification_callback=spoken.append)
        reminder = engine.create("물 마시기", datetime.now() + timedelta(minutes=1), remind_before=1)

        triggered = engine.tick(now=datetime.now())

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].id, reminder.id)
        self.assertEqual(spoken[0], "\ubb3c \ub9c8\uc2dc\uae30 \uc54c\ub9bc\uc785\ub2c8\ub2e4.")

    def test_reminder_ability_routes_through_tool_dispatcher(self):
        """Check Reminder Ability uses AbilityRegistry and ToolDispatcher."""
        engine = ReminderEngine(queue=ReminderQueue())
        ability_registry = AbilityRegistry()
        ability_registry.register(ReminderAbility(engine=engine))
        tool_registry = ToolRegistry()
        ability_registry.register_tools(tool_registry)

        result = ToolDispatcher(tool_registry).execute(
            ToolRequest(
                tool_name="reminder",
                input_data={"text": "내일 오후 3시에 아야 만나기 30분 전 알림 등록해"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(len(engine.list(state=REMINDER_PENDING)), 1)

    def test_calendar_create_creates_reminder_when_engine_is_injected(self):
        """Check Calendar create syncs to ReminderEngine."""
        engine = ReminderEngine(queue=ReminderQueue())
        provider = MockCalendarProvider(events=[])
        ability = CalendarAbility(
            provider=provider,
            reminder_engine=engine,
            now_provider=lambda: datetime(2026, 7, 9, 18, 0, 0),
        )

        result = ability.execute(
            {
                "action": "create",
                "date": "2026-07-10",
                "time": "15:00",
                "title": "아야 만나기",
                "raw_text": "내일 오후 3시에 아야 만나기 30분 전에 알려줘",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        reminders = engine.list(state=REMINDER_PENDING)
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].title, "아야 만나기")
        self.assertEqual(reminders[0].datetime, "2026-07-10T15:00:00")
        self.assertEqual(reminders[0].remind_before, 30)
        self.assertEqual(reminders[0].source, "calendar")
        self.assertEqual(reminders[0].calendar_id, result.data.events[0].id)
        self.assertEqual(reminders[0].trigger_time, "2026-07-10T14:30:00")
        self.assertEqual(reminders[0].status, REMINDER_PENDING)

    def test_calendar_create_past_today_time_asks_tomorrow_confirmation(self):
        """Check past same-day calendar creates are not saved before confirmation."""
        now = datetime(2026, 7, 13, 18, 19, 0)
        engine = ReminderEngine(queue=ReminderQueue())
        provider = MockCalendarProvider(events=[])
        ability = CalendarAbility(provider=provider, reminder_engine=engine, now_provider=lambda: now)

        result = ability.execute(
            {
                "action": "create",
                "date": "2026-07-13",
                "time": "15:00",
                "title": "약속",
                "raw_text": "3시에 약속 잡아 줘",
            }
        )

        self.assertTrue(result.success)
        self.assertIn("이미 지났습니다", result.data.to_natural_language())
        self.assertIn("내일 오후 3시", result.data.to_natural_language())
        self.assertEqual(result.metadata["permission"], "confirm_required")
        self.assertEqual(result.metadata["query"].date, "2026-07-14")
        self.assertEqual(provider.events, [])
        self.assertEqual(engine.list(state=REMINDER_PENDING), [])

    def test_calendar_confirmed_past_time_is_blocked(self):
        """Check confirmed stale calendar input still cannot create events."""
        now = datetime(2026, 7, 13, 18, 19, 0)
        engine = ReminderEngine(queue=ReminderQueue())
        provider = MockCalendarProvider(events=[])
        ability = CalendarAbility(provider=provider, reminder_engine=engine, now_provider=lambda: now)

        result = ability.execute(
            {
                "action": "create",
                "date": "2026-07-13",
                "time": "15:00",
                "title": "약속",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        self.assertFalse(result.data.success)
        self.assertIn("다른 시간을 말씀해 주세요", result.data.to_natural_language())
        self.assertEqual(provider.events, [])
        self.assertEqual(engine.list(state=REMINDER_PENDING), [])

    def test_reminder_queue_deduplicates_same_calendar_trigger(self):
        """Check duplicate reminders with the same calendar trigger are not enqueued."""
        engine = ReminderEngine(queue=ReminderQueue())

        first = engine.create(
            "아야 만나기",
            "2026-07-10T15:00:00",
            remind_before=30,
            source="calendar",
            source_id="calendar-123",
        )
        second = engine.create(
            "아야 만나기",
            "2026-07-10T15:00:00",
            remind_before=30,
            source="calendar",
            source_id="calendar-123",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(engine.list(state=REMINDER_PENDING)), 1)

    def test_calendar_delete_cancels_reminder_when_engine_is_injected(self):
        """Check Calendar delete cancels matching reminder."""
        engine = ReminderEngine(queue=ReminderQueue())
        provider = MockCalendarProvider(events=[])
        ability = CalendarAbility(
            provider=provider,
            reminder_engine=engine,
            now_provider=lambda: datetime(2026, 7, 9, 18, 0, 0),
        )
        create_result = ability.execute(
            {
                "action": "create",
                "date": "2026-07-10",
                "time": "15:00",
                "title": "아야 만나기",
                "_confirmed": True,
            }
        )
        event_id = create_result.data.events[0].id
        self.assertEqual(len(engine.list(state=REMINDER_PENDING)), 1)

        delete_result = ability.execute({"action": "delete", "title": "아야", "_confirmed": True})

        self.assertTrue(delete_result.success)
        self.assertEqual(engine.queue.get(engine.list()[0].id).source_id, event_id)
        self.assertEqual(len(engine.list(state=REMINDER_PENDING)), 0)
        self.assertEqual(len(engine.list(state=REMINDER_CANCELLED)), 1)

    def test_default_registry_registers_reminder_ability(self):
        """Check default ToolRegistry exposes Reminder Ability."""
        registry = create_default_tool_registry()

        self.assertTrue(registry.exists("reminder"))


if __name__ == "__main__":
    unittest.main()
