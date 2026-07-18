import unittest

from jarvis.brain import EXECUTION_STATUS_CANCELLED, ExecutionContext, IntentRuntime, RetryPolicy
from jarvis.brain.execution_engine import execute_parallel
from jarvis.brain.planner import Plan, PlanStep
from jarvis.diagnostics.runtime_console import RuntimeDevConsole
from jarvis.tools import ToolDispatcher, create_default_tool_registry


class TestExecutionEngineEnhancement(unittest.TestCase):
    """Test v0.5.0 Beta.4 execution engine contracts."""

    def test_retry_policy_defaults_to_zero_retries(self):
        """Check default retry policy does not retry."""
        policy = RetryPolicy()

        self.assertEqual(policy.max_retries, 0)
        self.assertFalse(policy.should_retry(0))

    def test_runtime_result_contains_execution_metrics(self):
        """Check RuntimeResult exposes execution timing and retry metrics."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("what time is it")

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.execution_time, 0.0)
        self.assertGreaterEqual(result.router_time, 0.0)
        self.assertGreaterEqual(result.dispatcher_time, 0.0)
        self.assertEqual(result.retry_count, 0)
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.diagnostics.metrics.retry_count, 0)

    def test_plan_step_timeout_contract_exists(self):
        """Check PlanStep reserves timeout_ms."""
        step = PlanStep(tool="time.lookup", timeout_ms=500)

        self.assertEqual(step.timeout_ms, 500)
        self.assertEqual(step.to_dict()["timeout_ms"], 500)

    def test_execution_context_contract(self):
        """Check ExecutionContext carries plan execution metadata."""
        plan = Plan(goal="time.lookup", steps=(PlanStep(tool="time.lookup"),))
        context = ExecutionContext(
            plan=plan,
            step=plan.steps[0],
            retry_count=0,
            deadline=123,
            metadata={"runtime_id": "R1"},
        )

        payload = context.to_dict()
        self.assertEqual(payload["plan"]["goal"], "time.lookup")
        self.assertEqual(payload["step"]["tool"], "time.lookup")
        self.assertEqual(payload["retry_count"], 0)
        self.assertEqual(payload["deadline"], 123)
        self.assertEqual(payload["metadata"]["runtime_id"], "R1")

    def test_parallel_execution_placeholder_exists(self):
        """Check parallel execution is reserved but not implemented."""
        plan = Plan(goal="time.lookup")

        with self.assertRaises(NotImplementedError):
            execute_parallel(plan)

    def test_runtime_parallel_method_exists(self):
        """Check Runtime exposes the parallel placeholder."""
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(create_default_tool_registry()))

        with self.assertRaises(NotImplementedError):
            runtime.execute_parallel(Plan(goal="time.lookup"))

    def test_cancelled_status_constant_exists(self):
        """Check cancellation status is reserved."""
        self.assertEqual(EXECUTION_STATUS_CANCELLED, "CANCELLED")

    def test_runtime_console_renders_execution_metrics(self):
        """Check dev console shows execution metrics."""
        dispatcher = ToolDispatcher(registry=create_default_tool_registry())
        runtime = IntentRuntime(tool_dispatcher=dispatcher)

        result = runtime.run("what time is it")
        output = RuntimeDevConsole().render(result)

        self.assertIn("Execution", output)
        self.assertIn("Execution Time", output)
        self.assertIn("Router Time", output)
        self.assertIn("Dispatcher Time", output)
        self.assertIn("Retry", output)
        self.assertIn("Count : 0", output)
        self.assertIn("Timeout", output)
        self.assertIn("Fallback", output)
        self.assertIn("used: false", output)


if __name__ == "__main__":
    unittest.main()
