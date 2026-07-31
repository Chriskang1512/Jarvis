import json
import unittest
from datetime import datetime, timezone

from jarvis.goals import GoalParser
from jarvis.native_task_graph import (
    ArtifactPolicy,
    BindingSourceType,
    EdgeType,
    GoalSpecificationGraphMapper,
    GraphExecutionPolicy,
    GraphOutput,
    InputBinding,
    NativeTaskGraph,
    NativeTaskGraphBuilder,
    NativeTaskGraphSerializer,
    NativeTaskGraphValidator,
    NodeType,
    OutputDefinition,
    TaskEdge,
    TaskNode,
)
from jarvis.runtime.intent import IntentContext


NOW = datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc)


def node(node_id, capability="system.test", operation="run", outputs=None, **kwargs):
    return TaskNode(
        node_id=node_id,
        node_type=NodeType.CAPABILITY,
        capability_id=capability,
        operation=operation,
        outputs=outputs or {},
        **kwargs,
    )


def codes(report):
    return {issue.code for issue in report.errors}


class TestNativeTaskGraphFoundation(unittest.TestCase):
    def test_01_single_node_graph(self):
        graph = (
            NativeTaskGraphBuilder("g", "goal", "conversation")
            .add_node(node("weather", "weather.get_forecast", "get"))
            .build()
        )
        self.assertEqual(1, len(graph.nodes))
        self.assertEqual((), graph.nodes[0].dependencies)

    def test_02_sequential_three_node_graph(self):
        builder = NativeTaskGraphBuilder("g", "goal", "conversation")
        for item in ("a", "b", "c"):
            builder.add_node(node(item))
        graph = (
            builder.add_edge(TaskEdge("e1", "a", "b"))
            .add_edge(TaskEdge("e2", "b", "c"))
            .build()
        )
        self.assertEqual(("a",), graph.node("b").dependencies)
        self.assertEqual(("b",), graph.node("c").dependencies)

    def test_03_node_output_binding(self):
        forecast = OutputDefinition("forecast", "WeatherReport")
        builder = NativeTaskGraphBuilder("g", "goal", "conversation")
        builder.add_node(node("weather", outputs={"forecast": forecast}))
        builder.add_node(node("summary"))
        builder.bind_node_output(
            "summary",
            "source",
            "weather",
            "forecast",
            expected_type="WeatherReport",
        )
        builder.add_edge(TaskEdge("data", "weather", "summary", EdgeType.DATA))
        graph, report = builder.build_and_validate()
        self.assertTrue(report.is_valid)
        self.assertEqual(
            BindingSourceType.NODE_OUTPUT,
            graph.node("summary").inputs["source"].source_type,
        )

    def test_04_literal_binding(self):
        builder = NativeTaskGraphBuilder("g", "goal", "conversation")
        builder.add_node(node("condition"))
        builder.bind_literal("condition", "threshold", 50, expected_type="integer")
        self.assertEqual(50, builder.build().node("condition").inputs["threshold"].value)

    def test_05_context_slot_binding(self):
        builder = NativeTaskGraphBuilder("g", "goal", "conversation")
        builder.add_node(node("weather"))
        builder.bind_context_slot(
            "weather", "location", "location", expected_type="string"
        )
        binding = builder.build().node("weather").inputs["location"]
        self.assertEqual(BindingSourceType.CONTEXT_SLOT, binding.source_type)

    def test_06_artifact_reference_binding(self):
        builder = NativeTaskGraphBuilder("g", "goal", "conversation")
        builder.add_node(node("mail"))
        builder.bind_artifact_reference(
            "mail", "attachment", "report-ref", expected_type="ReportRef"
        )
        binding = builder.build().node("mail").inputs["attachment"]
        self.assertEqual(BindingSourceType.ARTIFACT_REFERENCE, binding.source_type)

    def test_07_duplicate_node_id_is_rejected_early(self):
        builder = NativeTaskGraphBuilder("g", "goal", "conversation").add_node(node("a"))
        with self.assertRaisesRegex(ValueError, "Duplicate NodeId"):
            builder.add_node(node("a"))

    def test_08_unknown_edge_reference_is_rejected(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(node("a"),),
            edges=(TaskEdge("e", "a", "missing"),),
        )
        self.assertIn(
            "EDGE_TARGET_NOT_FOUND", codes(NativeTaskGraphValidator().validate(graph))
        )

    def test_09_cycle_is_detected(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(node("a"), node("b")),
            edges=(TaskEdge("ab", "a", "b"), TaskEdge("ba", "b", "a")),
        )
        self.assertIn("CYCLE_DETECTED", codes(NativeTaskGraphValidator().validate(graph)))

    def test_10_unreachable_node_is_detected(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(node("entry"), node("next"), node("detached")),
            edges=(TaskEdge("e", "entry", "next"),),
        )
        report = NativeTaskGraphValidator().validate(graph)
        self.assertIn("UNREACHABLE_NODE", codes(report))

    def test_11_output_key_mismatch_is_detected(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(
                node("source", outputs={"actual": OutputDefinition("actual", "string")}),
                node(
                    "target",
                    inputs={
                        "input": InputBinding(
                            BindingSourceType.NODE_OUTPUT,
                            source_node_id="source",
                            source_key="missing",
                            expected_type="string",
                        )
                    },
                ),
            ),
            edges=(TaskEdge("e", "source", "target", EdgeType.DATA),),
        )
        self.assertIn(
            "SOURCE_OUTPUT_NOT_FOUND", codes(NativeTaskGraphValidator().validate(graph))
        )

    def test_12_type_mismatch_is_detected(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(
                node("source", outputs={"count": OutputDefinition("count", "integer")}),
                node(
                    "target",
                    inputs={
                        "text": InputBinding(
                            BindingSourceType.NODE_OUTPUT,
                            source_node_id="source",
                            source_key="count",
                            expected_type="string",
                        )
                    },
                ),
            ),
            edges=(TaskEdge("e", "source", "target", EdgeType.DATA),),
        )
        self.assertIn(
            "BINDING_TYPE_MISMATCH", codes(NativeTaskGraphValidator().validate(graph))
        )

    def test_13_required_input_missing_is_detected(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(node("weather", required_inputs=("location",)),),
        )
        self.assertIn(
            "REQUIRED_INPUT_MISSING", codes(NativeTaskGraphValidator().validate(graph))
        )

    def test_14_graph_output_reference_is_validated(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(node("weather"),),
            outputs=(GraphOutput("primary", "weather", "missing", "string"),),
        )
        self.assertIn(
            "GRAPH_OUTPUT_KEY_NOT_FOUND",
            codes(NativeTaskGraphValidator().validate(graph)),
        )

    def test_15_json_round_trip_and_unknown_fields(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(
                node(
                    "weather",
                    outputs={
                        "forecast": OutputDefinition("forecast", "WeatherReport")
                    },
                ),
            ),
            outputs=(
                GraphOutput(
                    "primary",
                    "weather",
                    "forecast",
                    "WeatherReport",
                    is_primary=True,
                    artifact_policy=ArtifactPolicy.REFERENCE,
                ),
            ),
            created_at=NOW,
            updated_at=NOW,
        )
        payload = NativeTaskGraphSerializer.to_dict(graph)
        payload["futureField"] = {"supportedLater": True}
        restored = NativeTaskGraphSerializer.from_json(
            json.dumps(payload, ensure_ascii=False)
        )
        self.assertEqual(
            NativeTaskGraphSerializer.to_dict(graph),
            NativeTaskGraphSerializer.to_dict(restored),
        )

    def test_16_schema_version_snapshot(self):
        graph = NativeTaskGraph(
            "graph-1",
            "goal-1",
            "conversation-1",
            created_at=NOW,
            updated_at=NOW,
        )
        payload = NativeTaskGraphSerializer.to_dict(graph)
        self.assertEqual(
            {
                "schemaVersion": "1.0",
                "graphId": "graph-1",
                "goalId": "goal-1",
                "conversationId": "conversation-1",
                "version": 1,
                "nodes": [],
                "edges": [],
                "outputs": [],
                "metadata": {},
                "executionPolicy": {
                    "executionMode": "Sequential",
                    "maxNodeCount": 50,
                    "maxExecutionDurationSeconds": 300.0,
                    "allowParallelExecution": False,
                    "allowReplan": False,
                    "allowPartialCompletion": False,
                    "stopOnFailure": True,
                    "permissionStrategy": "Batch",
                },
                "createdAt": "2026-07-28T13:00:00+00:00",
                "updatedAt": "2026-07-28T13:00:00+00:00",
            },
            payload,
        )

    def test_17_builder_build_and_validate(self):
        graph, report = (
            NativeTaskGraphBuilder("g", "goal", "conversation")
            .add_node(node("result"))
            .build_and_validate()
        )
        self.assertEqual("g", graph.graph_id)
        self.assertTrue(report.is_valid)

    def test_18_goal_specification_maps_to_empty_skeleton(self):
        goal = GoalParser(clock=lambda: datetime(2026, 7, 28, 10, 0)).parse(
            "내일 강릉 날씨 알려줘",
            intent_context=IntentContext(
                current_date="2026-07-28", current_time="10:00:00"
            ),
        ).goal
        graph = GoalSpecificationGraphMapper().map(
            goal, conversation_id="conversation-1", graph_id="graph-fixed"
        )
        self.assertEqual(goal.goal_id, graph.goal_id)
        self.assertEqual("weather", graph.metadata["domain"])
        self.assertEqual((), graph.nodes)

    def test_19_direct_execution_route_is_unchanged(self):
        result = GoalParser(clock=lambda: datetime(2026, 7, 28, 10, 0)).parse(
            "내일 강릉 날씨 알려줘",
            intent_context=IntentContext(
                current_date="2026-07-28", current_time="10:00:00"
            ),
        )
        self.assertEqual("direct", result.route)

    def test_20_max_node_count_is_validated(self):
        graph = NativeTaskGraph(
            "g",
            "goal",
            "conversation",
            nodes=(node("a"), node("b")),
            edges=(TaskEdge("e", "a", "b"),),
            execution_policy=GraphExecutionPolicy(max_node_count=1),
        )
        self.assertIn(
            "MAX_NODE_COUNT_EXCEEDED",
            codes(NativeTaskGraphValidator().validate(graph)),
        )

    def test_invalid_binding_combinations_are_rejected_at_creation(self):
        with self.assertRaisesRegex(ValueError, "Literal binding"):
            InputBinding(
                BindingSourceType.LITERAL,
                source_node_id="source",
                value=1,
            )
        with self.assertRaisesRegex(ValueError, "requires source_node_id"):
            InputBinding(
                BindingSourceType.NODE_OUTPUT,
                source_key="value",
            )


if __name__ == "__main__":
    unittest.main()
