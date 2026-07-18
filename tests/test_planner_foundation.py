import unittest

from jarvis.brain import Intent, IntentRuntime, Plan, Planner, PlanStep
from jarvis.brain.planner import STEP_STATUS_COMPLETED, STEP_STATUS_PENDING
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.diagnostics.runtime_console import RuntimeDevConsole
from jarvis.tools import ToolDispatcher, create_default_tool_registry


class TestPlannerFoundation(unittest.TestCase):
    """Test v0.5.0 Beta.3 Planner Foundation."""

    def test_planner_creates_single_step_plan(self):
        """Check one intent becomes one plan step."""
        intent = Intent(
            name="time.lookup",
            confidence=0.95,
            parameters={},
            tool_name="time",
        )

        plan = Planner().plan(intent)

        self.assertIsInstance(plan, Plan)
        self.assertTrue(plan.id.startswith("P-"))
        self.assertEqual(plan.goal, "time.lookup")
        self.assertEqual(plan.status, "CREATED")
        self.assertEqual(len(plan.steps), 1)
        self.assertIsInstance(plan.steps[0], PlanStep)
        self.assertEqual(plan.steps[0].tool, "time.lookup")
        self.assertEqual(plan.steps[0].status, STEP_STATUS_PENDING)

    def test_runtime_executes_through_planner(self):
        """Check RuntimeResult contains the generated plan."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("what time is it")

        self.assertTrue(result.success)
        self.assertEqual(result.plan.goal, "time.lookup")
        self.assertEqual(result.plan.steps[0].tool, "time.lookup")
        self.assertEqual(result.plan.steps[0].status, STEP_STATUS_COMPLETED)
        self.assertEqual(result.tool, "time")

    def test_runtime_publishes_plan_events(self):
        """Check planner lifecycle events are published."""
        diagnostics = DiagnosticsCollector()
        dispatcher = ToolDispatcher(
            registry=create_default_tool_registry(diagnostics_collector=diagnostics),
            diagnostics_collector=diagnostics,
        )
        runtime = IntentRuntime(tool_dispatcher=dispatcher, diagnostics_collector=diagnostics)

        runtime.run("what time is it")

        event_types = [event.event_type for event in diagnostics.get_snapshot().published_events]
        self.assertIn("plan.created", event_types)
        self.assertIn("plan.started", event_types)
        self.assertIn("plan.completed", event_types)

    def test_empty_plan_falls_back(self):
        """Check an empty plan leaves Runtime unhandled for fallback."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(
            tool_dispatcher=dispatcher,
            planner=EmptyPlanner(),
        )

        result = runtime.run("what time is it")

        self.assertFalse(result.handled)
        self.assertFalse(result.success)
        self.assertEqual(result.plan.status, "EMPTY")
        self.assertEqual(result.diagnostics.execution_result, "empty_plan")

    def test_runtime_console_renders_plan(self):
        """Check dev console shows plan goal and steps."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("what time is it")
        output = RuntimeDevConsole().render(result)

        self.assertIn("Plan", output)
        self.assertIn("ID", output)
        self.assertIn(result.plan.id, output)
        self.assertIn("Goal", output)
        self.assertIn("time.lookup", output)
        self.assertIn("Steps", output)
        self.assertIn("[1] time.lookup", output)
        self.assertIn("Status : COMPLETED", output)


class EmptyPlanner:
    """Planner test double that returns no steps."""

    def plan(self, intent):
        """Return an empty plan."""
        return Plan(goal=intent.name, steps=(), status="EMPTY")


if __name__ == "__main__":
    unittest.main()
