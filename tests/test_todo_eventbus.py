import unittest

from jarvis.core.events import InMemoryEventBus, ReminderScheduleHandler
from jarvis.core.todos import TodoRepository
from jarvis.native.reminder.engine import ReminderEngine


class TodoEventBusTest(unittest.TestCase):
    def test_todo_created_schedules_reminder_through_eventbus(self):
        reminder_engine = ReminderEngine()
        event_bus = InMemoryEventBus()
        event_bus.subscribe("TodoCreated", ReminderScheduleHandler(reminder_engine, event_bus=event_bus))
        repository = TodoRepository(event_bus=event_bus)

        todo = repository.create("약 사기", due_at="2999-01-01T17:00:00")

        reminders = reminder_engine.list()
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].title, "약 사기")
        self.assertEqual(reminders[0].source, "todo")
        self.assertEqual(reminders[0].source_id, todo.id)

    def test_todo_completed_cancels_related_reminder(self):
        reminder_engine = ReminderEngine()
        event_bus = InMemoryEventBus()
        handler = ReminderScheduleHandler(reminder_engine, event_bus=event_bus)
        event_bus.subscribe("TodoCreated", handler)
        event_bus.subscribe("TodoCompleted", handler)
        repository = TodoRepository(event_bus=event_bus)

        todo = repository.create("약 사기", due_at="2999-01-01T17:00:00")
        self.assertEqual(len(reminder_engine.list(state="pending")), 1)

        repository.complete(todo.id)
        self.assertEqual(len(reminder_engine.list(state="pending")), 0)


if __name__ == "__main__":
    unittest.main()
