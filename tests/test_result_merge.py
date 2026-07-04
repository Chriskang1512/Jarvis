import inspect
import unittest
from dataclasses import FrozenInstanceError

from jarvis.execution import ExecutionGraphRunner
from jarvis.execution.contracts import ExecutionNodeResult, ExecutionRunResult
from jarvis.result_merge import ResultMerger
from jarvis.result_merge import DefaultResultMerger, UnifiedResult
from jarvis.result_merge import default as merge_module


class TestResultMerge(unittest.TestCase):
    """Test v0.4 Beta.4 Result Merge Engine."""

    def test_default_merger_merges_success_warning_and_error(self):
        """Check merge rules split results, warnings, and errors."""
        execution_result = [
            {
                "capability": "finance",
                "status": "success",
                "result": "VOO +0.8%",
                "started_at": "2026-07-04T15:00:00.000",
                "finished_at": "2026-07-04T15:00:00.125",
            },
            {
                "capability": "weather",
                "status": "warning",
                "result": {"warning": "Rain likely"},
                "started_at": "2026-07-04T15:00:00.125",
                "finished_at": "2026-07-04T15:00:00.200",
            },
            {
                "capability": "calendar",
                "status": "failed",
                "result": {"error": "Calendar unavailable"},
                "started_at": "2026-07-04T15:00:00.200",
                "finished_at": "2026-07-04T15:00:00.300",
            },
        ]

        unified = DefaultResultMerger().merge(execution_result).to_dict()

        self.assertEqual(unified["summary"], "1 capabilities completed, 1 warnings, 1 errors")
        self.assertEqual(unified["results"][0]["capability"], "finance")
        self.assertEqual(unified["results"][0]["result"], "VOO +0.8%")
        self.assertEqual(unified["warnings"][0]["message"], "Rain likely")
        self.assertEqual(unified["errors"][0]["message"], "Calendar unavailable")
        self.assertEqual(unified["metadata"]["node_count"], 3)
        self.assertEqual(unified["metadata"]["result_count"], 1)
        self.assertEqual(unified["metadata"]["warning_count"], 1)
        self.assertEqual(unified["metadata"]["error_count"], 1)

    def test_merger_preserves_execution_metadata(self):
        """Check execution ID, plan ID, node count, timestamp, and timings remain visible."""
        execution_result = ExecutionRunResult(
            execution_id="exec_test",
            plan_id="plan_test",
            status="completed",
            results=[
                ExecutionNodeResult(
                    node_id="finance_001",
                    capability="finance",
                    status="completed",
                    result="VOO +0.8%",
                    started_at="2026-07-04T15:00:00.000",
                    finished_at="2026-07-04T15:00:01.000",
                )
            ],
        )

        unified = DefaultResultMerger().merge(
            execution_result.results,
            metadata={
                "execution_id": execution_result.execution_id,
                "plan_id": execution_result.plan_id,
                "status": execution_result.status,
            },
        ).to_dict()

        self.assertEqual(unified["metadata"]["execution_id"], "exec_test")
        self.assertEqual(unified["metadata"]["plan_id"], "plan_test")
        self.assertEqual(unified["metadata"]["status"], "completed")
        self.assertEqual(unified["metadata"]["elapsed_ms"], 1000)
        self.assertEqual(unified["metadata"]["node_count"], 1)
        self.assertEqual(unified["metadata"]["completed_nodes"], 1)
        self.assertEqual(unified["metadata"]["failed_nodes"], 0)
        self.assertIn("timestamp", unified["metadata"])
        self.assertEqual(unified["metadata"]["nodes"][0]["duration_ms"], 1000)
        self.assertEqual(unified["results"][0]["metadata"]["duration_ms"], 1000)

    def test_result_merger_interface_uses_result_list(self):
        """Check ResultMerger defines the swappable list-to-unified contract."""
        self.assertTrue(issubclass(DefaultResultMerger, ResultMerger))

    def test_unified_result_is_frozen_after_merge(self):
        """Check UnifiedResult cannot be reassigned after merge."""
        unified = DefaultResultMerger().merge(
            [
                {
                    "capability": "finance",
                    "status": "success",
                    "result": "VOO +0.8%",
                }
            ]
        )

        with self.assertRaises(FrozenInstanceError):
            unified.summary = "changed"

        with self.assertRaises(TypeError):
            unified.metadata["execution_id"] = "changed"

        with self.assertRaises(TypeError):
            unified.results[0]["result"] = "changed"

    def test_unified_result_is_voice_and_ui_ready(self):
        """Check Voice can read summary and UI can render detailed lists."""
        unified = DefaultResultMerger().merge(
            [
                {
                    "capability": "finance",
                    "status": "success",
                    "result": "VOO +0.8%",
                },
                {
                    "capability": "weather",
                    "status": "warning",
                    "result": {"warning": "Rain likely"},
                },
            ],
            metadata={"execution_id": "exec_ui"},
        )
        payload = unified.to_dict()

        self.assertIsInstance(unified.summary, str)
        self.assertEqual(payload["summary"], "1 capabilities completed, 1 warnings")
        self.assertEqual(payload["results"][0]["capability"], "finance")
        self.assertEqual(payload["warnings"][0]["capability"], "weather")
        self.assertEqual(payload["metadata"]["execution_id"], "exec_ui")

    def test_summary_keeps_warning_and_error_details_out_of_voice_text(self):
        """Check summary reports counts without mixing in detailed issue messages."""
        unified = DefaultResultMerger().merge(
            [
                {
                    "capability": "weather",
                    "status": "warning",
                    "result": {"warning": "Rain likely after 15:00"},
                },
                {
                    "capability": "calendar",
                    "status": "failed",
                    "result": {"error": "Calendar token expired"},
                },
            ]
        )

        self.assertEqual(unified.summary, "0 capabilities completed, 1 warnings, 1 errors")
        self.assertNotIn("Rain likely", unified.summary)
        self.assertNotIn("Calendar token expired", unified.summary)
        self.assertEqual(unified.warnings[0]["message"], "Rain likely after 15:00")
        self.assertEqual(unified.errors[0]["message"], "Calendar token expired")

    def test_result_order_follows_plan_execution_order(self):
        """Check capability result order is preserved from execution order."""
        unified = DefaultResultMerger().merge(
            [
                {
                    "node_id": "finance_001",
                    "capability": "finance",
                    "status": "completed",
                    "result": "finance result",
                },
                {
                    "node_id": "calendar_002",
                    "capability": "calendar",
                    "status": "completed",
                    "result": "calendar result",
                },
                {
                    "node_id": "weather_003",
                    "capability": "weather",
                    "status": "completed",
                    "result": "weather result",
                },
            ]
        )

        self.assertEqual(
            [result["capability"] for result in unified.results],
            ["finance", "calendar", "weather"],
        )
        self.assertEqual(
            [result["node_id"] for result in unified.results],
            ["finance_001", "calendar_002", "weather_003"],
        )

    def test_runner_can_return_unified_response_without_changing_run_contract(self):
        """Check ExecutionGraph can connect to Merge through run_unified."""
        runner = ExecutionGraphRunner(
            capability_router=StaticRouter(),
            dispatcher=StaticDispatcher(),
        )
        plan = {
            "plan_id": "plan_test",
            "graph": {
                "nodes": [
                    {
                        "id": "finance_001",
                        "capability": "finance",
                        "input": "VOO",
                    }
                ],
                "edges": [],
                "metadata": {},
            },
        }

        raw = runner.run(plan).to_dict()
        unified = runner.run_unified(plan)

        self.assertNotIn("summary", raw)
        self.assertIsInstance(unified, UnifiedResult)
        self.assertEqual(unified.results[0]["capability"], "finance")
        self.assertEqual(unified.results[0]["result"], "VOO +0.8%")
        self.assertEqual(unified.metadata["plan_id"], "plan_test")
        self.assertEqual(unified.metadata["completed_nodes"], 1)
        self.assertEqual(unified.summary, "1 capabilities completed")

    def test_run_unified_preserves_partial_results_when_one_node_fails(self):
        """Check unified response keeps successes and errors from a failed run."""
        runner = ExecutionGraphRunner(
            capability_router=StaticRouter(),
            dispatcher=PartiallyFailingDispatcher(),
        )
        plan = {
            "plan_id": "plan_partial",
            "graph": {
                "nodes": [
                    {
                        "id": "finance_001",
                        "capability": "finance",
                        "input": "success",
                    },
                    {
                        "id": "calendar_002",
                        "capability": "calendar",
                        "input": "fail",
                    },
                    {
                        "id": "weather_003",
                        "capability": "weather",
                        "input": "success",
                    },
                ],
                "edges": [],
                "metadata": {},
            },
        }

        unified = runner.run_unified(plan)

        self.assertEqual(unified.summary, "2 capabilities completed, 1 errors")
        self.assertEqual([result["capability"] for result in unified.results], ["finance", "weather"])
        self.assertEqual(unified.errors[0]["capability"], "calendar")
        self.assertEqual(unified.errors[0]["message"], "Calendar unavailable")
        self.assertEqual(unified.metadata["plan_id"], "plan_partial")
        self.assertEqual(unified.metadata["status"], "failed")
        self.assertEqual(unified.metadata["node_count"], 3)
        self.assertEqual(unified.metadata["completed_nodes"], 2)
        self.assertEqual(unified.metadata["failed_nodes"], 1)

    def test_metadata_is_diagnostics_console_ready(self):
        """Check metadata exposes run and node fields diagnostics can render."""
        unified = DefaultResultMerger().merge(
            [
                {
                    "node_id": "finance_001",
                    "capability": "finance",
                    "status": "completed",
                    "result": "VOO +0.8%",
                    "started_at": "2026-07-04T15:00:00.000",
                    "finished_at": "2026-07-04T15:00:00.500",
                }
            ],
            metadata={
                "execution_id": "exec_diag",
                "plan_id": "plan_diag",
                "status": "completed",
            },
        )
        metadata = unified.to_dict()["metadata"]

        self.assertEqual(metadata["execution_id"], "exec_diag")
        self.assertEqual(metadata["plan_id"], "plan_diag")
        self.assertEqual(metadata["elapsed_ms"], 500)
        self.assertEqual(metadata["nodes"][0]["node_id"], "finance_001")
        self.assertEqual(metadata["nodes"][0]["capability"], "finance")
        self.assertEqual(metadata["nodes"][0]["status"], "completed")
        self.assertEqual(metadata["nodes"][0]["duration_ms"], 500)

    def test_merger_does_not_import_forbidden_layers(self):
        """Check Merge only handles results and does not plan, execute, or call tools."""
        source = inspect.getsource(merge_module)
        forbidden = [
            "jarvis.planner",
            "IntentPlanner",
            "PlanValidator",
            "ToolDispatcher",
            "ToolRegistry",
            "jarvis.memory",
            "memory_store",
            "jarvis.capabilities.finance",
            "jarvis.capabilities.japanese",
            "jarvis.capabilities.creator",
            "jarvis.capabilities.hotel",
            "jarvis.capabilities.life",
            ".execute(",
            ".route(",
        ]

        for value in forbidden:
            self.assertNotIn(value, source)


class StaticRouter:
    """Router stub for merge integration tests."""

    def route(self, node, context=None):
        """Return the node as the executable request."""
        return node


class StaticDispatcher:
    """Dispatcher stub for merge integration tests."""

    def execute(self, request):
        """Return one successful tool result."""

        class Result:
            success = True
            output = "VOO +0.8%"

        return Result()


class PartiallyFailingDispatcher:
    """Dispatcher stub that keeps later nodes runnable after one failure."""

    def execute(self, request):
        """Return success unless the node requests a failure."""

        class Result:
            success = request.get("input") != "fail"
            output = f"{request.get('capability')} result"
            error = "Calendar unavailable"

        return Result()


if __name__ == "__main__":
    unittest.main()
