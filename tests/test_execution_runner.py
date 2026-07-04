import inspect
import unittest
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

from jarvis.capabilities import CapabilityLoader
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.execution import ExecutionContext, ExecutionGraphRunner, MetadataCapabilityRouter, NodeStatus
from jarvis.execution import runner as runner_module
from jarvis.planner import IntentPlanner, PlanValidator
from jarvis.tools import ToolDispatcher, create_default_tool_registry


class TestExecutionGraphRunner(unittest.TestCase):
    """Test v0.4 Beta.2 Execution Graph Runtime."""

    def test_runner_executes_validated_life_plan_sequentially(self):
        """Check Runner executes ordered nodes and returns ordered results."""
        plan, runner, _diagnostics = create_life_execution_context()

        result = runner.run(plan).to_dict()

        self.assertTrue(result["execution_id"].startswith("exec_"))
        self.assertEqual(result["plan_id"], plan.to_dict()["plan_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["node_id"], "life_001")
        self.assertEqual(result["results"][0]["status"], "completed")
        self.assertEqual(result["results"][1]["node_id"], "life_002")
        self.assertEqual(result["results"][1]["status"], "completed")
        self.assertIn("result", result["results"][0])
        self.assertIn("started_at", result["results"][0])
        self.assertIn("finished_at", result["results"][0])

    def test_runner_does_not_merge_outputs(self):
        """Check Beta.2 returns ordered node results without merge output."""
        plan, runner, _diagnostics = create_life_execution_context()

        result = runner.run(plan).to_dict()

        self.assertIn("results", result)
        self.assertNotIn("merged", result)
        self.assertNotIn("summary", result)

    def test_runner_does_not_modify_graph_structure(self):
        """Check Runner walks graph without changing the plan graph."""
        plan, runner, _diagnostics = create_life_execution_context()
        original_graph = deepcopy(plan.to_dict()["graph"])

        runner.run(plan)

        self.assertEqual(plan.to_dict()["graph"], original_graph)

    def test_runner_records_diagnostics_events(self):
        """Check Runner emits execution trace events for diagnostics."""
        plan, runner, diagnostics = create_life_execution_context()

        runner.run(plan)

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn(f"[PLAN] {plan.to_dict()['plan_id']}", messages)
        self.assertIn("[RUNNER] life_001 RUNNING", messages)
        self.assertTrue(any(message.startswith("[RUNNER] life_001 COMPLETED") for message in messages))
        self.assertIn("[RUNNER] life_002 RUNNING", messages)
        self.assertTrue(any(message.startswith("[RUNNER] life_002 COMPLETED") for message in messages))
        self.assertIn("Execution Summary", messages)
        self.assertIn("Nodes: 2", messages)
        self.assertIn("Completed: 2", messages)
        self.assertIn("Failed: 0", messages)
        self.assertIn("Context updated", messages)
        self.assertIn("Execution Context destroyed", messages)

    def test_runner_passes_previous_result_through_execution_context(self):
        """Check sequential nodes receive previous node results through input."""
        plan = {
            "plan_id": "plan_context",
            "graph": {
                "nodes": [
                    {"id": "first_001", "input": "first"},
                    {"id": "second_002", "input": "second"},
                ],
                "edges": [],
                "metadata": {},
            },
        }
        router = RecordingRouter()
        dispatcher = EchoDispatcher()
        runner = ExecutionGraphRunner(capability_router=router, dispatcher=dispatcher)

        result = runner.run(plan).to_dict()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(router.seen_context_values[0], {})
        self.assertIn("first_001", router.seen_context_values[1])
        self.assertEqual(router.seen_context_values[1]["first_001"]["result"]["echo"], "first")
        self.assertTrue(router.context.destroyed)

    def test_router_builds_execution_input_data_contract(self):
        """Check routed tools receive the stable InputData contract."""
        plan, _runner, _diagnostics = create_life_execution_context()
        _capability_registry, tool_registry = create_runtime_registries()
        router = MetadataCapabilityRouter(tool_registry)
        context = ExecutionContext(execution_id="exec_test")
        context.store_result("life_001", {"hello": "world"})

        request = router.route(plan.to_dict()["graph"]["nodes"][1], context=context)

        self.assertIn("text", request.input_data)
        self.assertIn("user_input", request.input_data)
        self.assertIn("previous_results", request.input_data)
        self.assertIn("execution_snapshot", request.input_data)
        self.assertEqual(request.input_data["execution_snapshot"]["context_version"], "1.0")
        self.assertEqual(request.input_data["previous_results"], [{"hello": "world"}])

    def test_execution_snapshot_is_immutable(self):
        """Check capabilities cannot mutate the execution snapshot."""
        context = ExecutionContext(execution_id="exec_test")
        context.store_result("life_001", {"hello": "world"})
        snapshot = context.snapshot()

        self.assertIsInstance(snapshot, MappingProxyType)
        self.assertEqual(snapshot["context_version"], "1.0")
        with self.assertRaises(TypeError):
            snapshot["values"] = {}

        with self.assertRaises(TypeError):
            snapshot["values"]["life_001"]["result"]["hello"] = "changed"

        self.assertEqual(context.values["life_001"]["result"]["hello"], "world")

    def test_runner_marks_failed_route(self):
        """Check Runner records failed node results when routing fails."""
        plan = {
            "plan_id": "plan_test",
            "graph": {
                "nodes": [
                    {
                        "id": "unknown_001",
                        "step": 1,
                        "capability": "unknown",
                        "intent": "unknown",
                        "input": "unknown",
                        "status": "CREATED",
                        "required": True,
                        "confidence": 0.1,
                    }
                ],
                "edges": [],
                "metadata": {},
            },
        }
        _capability_registry, tool_registry = create_runtime_registries()
        runner = ExecutionGraphRunner(
            capability_router=MetadataCapabilityRouter(tool_registry),
            dispatcher=ToolDispatcher(tool_registry),
        )

        result = runner.run(plan).to_dict()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["results"][0]["status"], "failed")
        self.assertIn("error", result["results"][0]["result"])

    def test_runner_architecture_does_not_import_forbidden_layers(self):
        """Check Runner does not import Planner, ToolRegistry, Memory, or capabilities."""
        source = inspect.getsource(runner_module)
        forbidden = [
            "jarvis.planner",
            "IntentPlanner",
            "PlanValidator",
            "ToolRegistry",
            "jarvis.memory",
            "memory_store",
            "jarvis.capabilities.finance",
            "jarvis.capabilities.japanese",
            "jarvis.capabilities.creator",
            "jarvis.capabilities.hotel",
            "jarvis.capabilities.life",
            "FinanceCapability",
            "JapaneseCapability",
            "CreatorCapability",
            "HotelCapability",
            "LifeCapability",
        ]

        for value in forbidden:
            self.assertNotIn(value, source)

    def test_capabilities_do_not_import_execution_context(self):
        """Check capabilities remain input-output and do not own execution context."""
        capability_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path("jarvis").joinpath("capabilities").rglob("*.py")
        )

        self.assertNotIn("ExecutionContext", capability_source)
        self.assertNotIn("jarvis.execution.context", capability_source)

    def test_node_status_lifecycle_values_exist(self):
        """Check node lifecycle states are reserved."""
        self.assertEqual(NodeStatus.CREATED.value, "CREATED")
        self.assertEqual(NodeStatus.RUNNING.value, "RUNNING")
        self.assertEqual(NodeStatus.COMPLETED.value, "COMPLETED")
        self.assertEqual(NodeStatus.FAILED.value, "FAILED")
        self.assertEqual(NodeStatus.SKIPPED.value, "SKIPPED")


def create_life_execution_context():
    """Create a validated Life plan and runner."""
    capability_registry, tool_registry = create_runtime_registries()
    plan = IntentPlanner(capability_registry).plan("오늘 할 일 정리하고 회고도 해줘")
    validation = PlanValidator(capability_registry).validate(plan)
    diagnostics = DiagnosticsCollector()

    if not validation["valid"]:
        raise AssertionError(validation["errors"])

    runner = ExecutionGraphRunner(
        capability_router=MetadataCapabilityRouter(tool_registry),
        dispatcher=ToolDispatcher(tool_registry),
        diagnostics_collector=diagnostics,
    )
    return plan, runner, diagnostics


def create_runtime_registries():
    """Create capability and tool registries for execution tests."""
    capability_registry = CapabilityLoader().load()
    tool_registry = create_default_tool_registry()
    capability_registry.register_tools(tool_registry)
    return capability_registry, tool_registry


class RecordingRouter:
    """Router stub that records context snapshots."""

    def __init__(self):
        """Create an empty recording router."""
        self.seen_context_values = []
        self.context = None

    def route(self, node, context=None):
        """Record context and return a simple request object."""
        self.context = context
        self.seen_context_values.append(deepcopy(mapping_to_dict(context.snapshot()["values"])))
        return {"node": node}


class EchoDispatcher:
    """Dispatcher stub that echoes node input."""

    def execute(self, request):
        """Return an object shaped like ToolResult."""
        node = request["node"]
        if "second" in node.get("input", ""):
            self.mark_context_destroyed_later = True

        class Result:
            success = True
            output = {"echo": node.get("input", "")}

        return Result()


def mapping_to_dict(value):
    """Convert read-only mappings to normal dictionaries for assertions."""
    if isinstance(value, MappingProxyType):
        return {
            key: mapping_to_dict(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [mapping_to_dict(item) for item in value]

    return value


if __name__ == "__main__":
    unittest.main()
