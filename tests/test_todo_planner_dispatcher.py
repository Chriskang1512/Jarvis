import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.todo import TodoAbility
from jarvis.core.events import InMemoryEventBus, ReminderScheduleHandler
from jarvis.core.todos import TodoRepository
from jarvis.native.reminder.engine import ReminderEngine
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools.registry import ToolRegistry


class TodoPlannerDispatcherTest(unittest.TestCase):
    def make_dispatcher(self):
        reminder_engine = ReminderEngine()
        event_bus = InMemoryEventBus()
        event_bus.subscribe("TodoCreated", ReminderScheduleHandler(reminder_engine, event_bus=event_bus))
        repository = TodoRepository(event_bus=event_bus)
        ability_registry = AbilityRegistry()
        ability_registry.register(TodoAbility(repository=repository))
        tool_registry = ToolRegistry()
        ability_registry.register_tools(tool_registry)
        return RuntimeToolDispatcher(tool_registry), repository, reminder_engine

    def test_planner_routes_todo_create(self):
        dispatcher, _, _ = self.make_dispatcher()

        plan = dispatcher.create_plan("우유 사기 추가해")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "todo")
        self.assertEqual(plan.steps[0].action, "create")

    def test_planner_routes_today_todo_list_before_reminder(self):
        dispatcher, _, _ = self.make_dispatcher()

        plan = dispatcher.create_plan("오늘 할일 알려줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "todo")
        self.assertEqual(plan.steps[0].action, "list")

    def test_planner_routes_numbered_todo_completion_before_ai(self):
        dispatcher, _, _ = self.make_dispatcher()

        plan = dispatcher.create_plan("1번, 3번 완료했어")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "todo")
        self.assertEqual(plan.steps[0].action, "complete")

    def test_dispatcher_executes_todo_create_with_reminder(self):
        dispatcher, repository, reminder_engine = self.make_dispatcher()
        plan = dispatcher.create_plan("내일 오후 5시에 약 사기 추가해")

        result = dispatcher.execute_plan(plan, confirmed=True)

        self.assertTrue(result.success)
        self.assertEqual(len(repository.list()), 1)
        self.assertEqual(repository.list()[0].title, "약 사기")
        self.assertEqual(len(reminder_engine.list(state="pending")), 1)


if __name__ == "__main__":
    unittest.main()
