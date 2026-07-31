import unittest
from dataclasses import replace

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.weather.ability import WeatherAbility
from jarvis.abilities.native.weather.provider import MockWeatherProvider
from jarvis.capability_planning import ExecutionPlanSnapshot
from jarvis.capability_planning.execution_snapshot import (
    PLANNER_METADATA_KEYS,
    canonical_hash,
    validation_projection,
)
from jarvis.core.events import InMemoryEventBus
from jarvis.graph_execution import (
    CapabilityExecutionAdapter,
    CURRENT_SESSION_VERSION,
    ExecutionWaitingReason,
    GraphExecutionState,
    GraphExecutor,
    NodeExecutionState,
    GraphExecutionSession,
)
from jarvis.native_task_graph import (
    BindingSourceType,
    EdgeType,
    GraphOutput,
    InputBinding,
    NativeTaskGraph,
    NativeTaskGraphSerializer,
    NativeTaskGraphValidator,
    NodeType,
    OutputDefinition,
    PermissionRequirement,
    TaskEdge,
    TaskNode,
)


class EventCollector:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)


def metadata():
    return {
        "capabilitySnapshotId": "capabilities-1",
        "registryHash": "registry-hash",
        "plannerType": "RulePlanner",
        "plannerVersion": "1.0",
        "planningPolicyVersion": "1.0",
    }


def validated_snapshot(graph, confidence=0.93):
    report = NativeTaskGraphValidator().validate(graph)
    assert report.is_valid, report.errors
    snapshot = ExecutionPlanSnapshot(
        graph_hash=canonical_hash(NativeTaskGraphSerializer.to_dict(graph)),
        planner_metadata=metadata(),
        planning_confidence=confidence,
        validation_hash=canonical_hash(validation_projection(report)),
    )
    return snapshot, report


def literal(value, expected_type="string"):
    return InputBinding(
        BindingSourceType.LITERAL,
        value=value,
        expected_type=expected_type,
    )


def node_output(node_id, key, expected_type="Any"):
    return InputBinding(
        BindingSourceType.NODE_OUTPUT,
        source_node_id=node_id,
        source_key=key,
        expected_type=expected_type,
    )


class TestGraphExecutorRuntime(unittest.TestCase):
    def test_existing_weather_ability_provider_is_called(self):
        class CountingWeatherProvider(MockWeatherProvider):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def get_weather(self, query):
                self.calls += 1
                return super().get_weather(query)

        provider = CountingWeatherProvider()
        registry = AbilityRegistry()
        registry.register(WeatherAbility(provider=provider))
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            inputs={
                "location": literal("강릉"),
                "date": literal("tomorrow"),
            },
            outputs={
                "forecast": OutputDefinition(
                    "forecast", "WeatherReport"
                )
            },
        )
        graph = NativeTaskGraph(
            "graph-real-weather",
            "goal-real-weather",
            "conversation",
            nodes=(node,),
            outputs=(
                GraphOutput(
                    "primary",
                    "weather",
                    "forecast",
                    "WeatherReport",
                ),
            ),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(registry)
        )

        result = executor.execute(graph, snapshot, report)

        self.assertEqual(1, provider.calls)
        self.assertEqual(
            "강릉",
            result.graph_outputs["primary"].location,
        )
        self.assertEqual(
            "tomorrow",
            result.graph_outputs["primary"].date,
        )

    def test_single_capability_executes_and_copies_snapshot_id(self):
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            inputs={"location": literal("강릉"), "date": literal("tomorrow")},
            outputs={"forecast": OutputDefinition("forecast", "WeatherReport")},
        )
        graph = NativeTaskGraph(
            "graph-weather",
            "goal-weather",
            "conversation",
            nodes=(node,),
            outputs=(GraphOutput("primary", "weather", "forecast", "WeatherReport"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "weather.get_forecast": lambda values: {
                        "location": values["location"],
                        "precipitation_probability": 70,
                    }
                }
            )
        )

        result = executor.execute(graph, snapshot, report)

        self.assertEqual(GraphExecutionState.SUCCEEDED, result.session.state)
        self.assertEqual(snapshot.snapshot_id, result.session.snapshot_id)
        self.assertEqual("강릉", result.graph_outputs["primary"]["location"])
        self.assertEqual(snapshot.snapshot_id, result.summary.snapshot_id)
        self.assertEqual(("weather",), result.summary.succeeded_nodes)
        self.assertEqual(1, result.summary.provider_calls)
        self.assertEqual(64, len(result.summary.result_hash))
        with self.assertRaises(AttributeError):
            result.session.snapshot_id = "changed"

    def test_node_output_is_passed_to_transform(self):
        search = TaskNode(
            "search",
            NodeType.CAPABILITY,
            "calendar.search_events",
            "search_events",
            inputs={"date": literal("tomorrow")},
            outputs={"events": OutputDefinition("events", "CalendarEventList")},
        )
        transform = TaskNode(
            "summary",
            NodeType.TRANSFORM,
            "system.format_result",
            "format_result",
            inputs={"source": node_output("search", "events", "CalendarEventList")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = NativeTaskGraph(
            "graph-summary",
            "goal-summary",
            "conversation",
            nodes=(search, transform),
            edges=(TaskEdge("search-summary", "search", "summary", EdgeType.DATA),),
            outputs=(GraphOutput("primary", "summary", "result", "string"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"calendar.search_events": lambda _: {"events": ["A", "B"]}}
            )
        )

        result = executor.execute(graph, snapshot, report)

        self.assertEqual("A\nB", result.graph_outputs["primary"])
        self.assertEqual(
            ["A", "B"],
            result.session.node_records["summary"].resolved_inputs["source"],
        )

    def test_permission_gate_pauses_and_resumes_same_session(self):
        node = TaskNode(
            "create",
            NodeType.CAPABILITY,
            "calendar.create_event",
            "create_event",
            inputs={
                "date": literal("tomorrow"),
                "time": literal("15:00"),
                "title": literal("아야 일정"),
            },
            outputs={"event": OutputDefinition("event", "CalendarEvent")},
            permission_requirement=PermissionRequirement.CONFIRM_REQUIRED,
        )
        graph = NativeTaskGraph(
            "graph-create",
            "goal-create",
            "conversation",
            nodes=(node,),
            outputs=(GraphOutput("primary", "create", "event", "CalendarEvent"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        calls = []
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"calendar.create_event": lambda values: calls.append(values) or {"id": "event-1"}}
            )
        )

        paused = executor.execute(graph, snapshot, report)
        paused_checkpoint = paused.session.to_checkpoint()

        self.assertEqual(
            ExecutionWaitingReason.WAITING_FOR_PERMISSION,
            paused.session.waiting_reason,
        )
        self.assertEqual(
            "WaitingForPermission",
            paused_checkpoint["waitingReason"],
        )
        self.assertIsNotNone(paused.session.waiting_since)
        self.assertEqual(
            paused.session.waiting_since.isoformat(),
            paused_checkpoint["waitingSince"],
        )
        restored_paused = GraphExecutionSession.from_checkpoint(
            paused_checkpoint, graph, snapshot
        )
        self.assertEqual(
            ExecutionWaitingReason.WAITING_FOR_PERMISSION,
            restored_paused.waiting_reason,
        )
        self.assertEqual(
            paused.session.waiting_since,
            restored_paused.waiting_since,
        )

        resumed = executor.execute(
            graph,
            snapshot,
            report,
            confirmed_node_ids=("create",),
            session=paused.session,
        )

        self.assertTrue(paused.requires_permission)
        self.assertEqual(paused.session.session_id, resumed.session.session_id)
        self.assertEqual(snapshot.snapshot_id, resumed.session.snapshot_id)
        self.assertEqual(1, len(calls))
        self.assertEqual(GraphExecutionState.SUCCEEDED, resumed.session.state)
        self.assertEqual(
            ExecutionWaitingReason.NONE,
            resumed.session.waiting_reason,
        )
        self.assertIsNone(resumed.session.waiting_since)
        self.assertIsNotNone(resumed.session.started_at)
        self.assertIsNotNone(resumed.session.completed_at)
        self.assertGreaterEqual(resumed.session.duration_seconds, 0.0)
        self.assertEqual(
            resumed.session.duration_seconds,
            resumed.summary.duration_seconds,
        )

    def test_false_condition_skips_action_and_completes_false_result(self):
        weather = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "WeatherReport")},
        )
        condition = TaskNode(
            "condition",
            NodeType.CONDITION,
            "system.condition",
            "condition",
            inputs={
                "value": node_output("weather", "forecast"),
                "expression": literal("rain_probability > 0"),
            },
            outputs={
                "result": OutputDefinition("result", "boolean"),
                "matched_branch": OutputDefinition("matched_branch", "string"),
                "evidence": OutputDefinition("evidence", "ConditionEvidence"),
                "actual_value": OutputDefinition("actual_value", "Any", False),
                "expected_value": OutputDefinition("expected_value", "Any", False),
                "operator": OutputDefinition("operator", "string"),
            },
        )
        reminder = TaskNode(
            "reminder",
            NodeType.CAPABILITY,
            "reminder.create",
            "create",
            outputs={"reminder": OutputDefinition("reminder", "Reminder")},
        )
        false_result = TaskNode(
            "false-result",
            NodeType.RESULT,
            "",
            "",
            inputs={"message": literal("비가 오지 않아 알림을 만들지 않았습니다.")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = NativeTaskGraph(
            "graph-condition",
            "goal-condition",
            "conversation",
            nodes=(weather, condition, reminder, false_result),
            edges=(
                TaskEdge("weather-condition", "weather", "condition", EdgeType.DATA),
                TaskEdge("condition-reminder", "condition", "reminder", EdgeType.CONDITIONAL_TRUE),
                TaskEdge("condition-false", "condition", "false-result", EdgeType.CONDITIONAL_FALSE),
            ),
            outputs=(GraphOutput("false", "false-result", "result", "string"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        reminder_calls = []
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "weather.get_forecast": lambda _: {"precipitation_probability": 0},
                    "reminder.create": lambda values: reminder_calls.append(values),
                }
            )
        )

        result = executor.execute(graph, snapshot, report)

        self.assertEqual(NodeExecutionState.SKIPPED, result.session.node_records["reminder"].state)
        self.assertEqual(NodeExecutionState.SUCCEEDED, result.session.node_records["false-result"].state)
        self.assertEqual([], reminder_calls)
        self.assertEqual("비가 오지 않아 알림을 만들지 않았습니다.", result.graph_outputs["false"])

    def test_events_checkpoint_and_timeline_share_snapshot_id(self):
        node = TaskNode(
            "contacts",
            NodeType.CAPABILITY,
            "contacts.search",
            "search",
            inputs={"query": literal("아야")},
            outputs={"contacts": OutputDefinition("contacts", "ContactList")},
        )
        graph = NativeTaskGraph(
            "graph-contacts",
            "goal-contacts",
            "conversation",
            nodes=(node,),
            outputs=(GraphOutput("primary", "contacts", "contacts", "ContactList"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        collector = EventCollector()
        bus = InMemoryEventBus()
        bus.subscribe("*", collector.handle)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"contacts.search": lambda _: {"contacts": ["aya@example.com"]}}
            ),
            event_bus=bus,
        )

        result = executor.execute(graph, snapshot, report, correlation_id="turn-1")

        event_types = [event.event_type for event in collector.events]
        self.assertEqual(
            [
                "runtime.execution.snapshot_verified",
                "runtime.execution.session_created",
                "runtime.execution.node_ready",
                "runtime.execution.node_started",
                "runtime.execution.verification_started",
                "runtime.execution.verification_passed",
                "runtime.execution.node_completed",
                "runtime.execution.goal_verification_started",
                "runtime.execution.goal_verification_completed",
                "runtime.execution.session_completed",
            ],
            event_types,
        )
        self.assertTrue(
            all(
                event.payload["snapshot_id"] == snapshot.snapshot_id
                for event in collector.events
            )
        )
        checkpoint = executor.checkpoint_store.checkpoints[result.session.session_id]
        self.assertEqual(snapshot.snapshot_id, checkpoint["snapshotId"])
        self.assertEqual(
            result.summary.result_hash,
            checkpoint["executionSummary"]["resultHash"],
        )
        self.assertEqual(
            result.summary.result_hash,
            collector.events[-1].payload["execution_summary"][
                "resultHash"
            ],
        )
        self.assertEqual(
            "session_completed", result.session.timeline[-1].event_type
        )

    def test_snapshot_failure_creates_no_session(self):
        node = TaskNode(
            "result",
            NodeType.RESULT,
            "",
            "",
            inputs={"message": literal("ok")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = NativeTaskGraph(
            "graph-result",
            "goal-result",
            "conversation",
            nodes=(node,),
            outputs=(GraphOutput("primary", "result", "result", "string"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        tampered = replace(snapshot, graph_hash="0" * 64)
        collector = EventCollector()
        bus = InMemoryEventBus()
        bus.subscribe("*", collector.handle)
        executor = GraphExecutor(CapabilityExecutionAdapter(), event_bus=bus)

        with self.assertRaises(ValueError):
            executor.execute(graph, tampered, report)

        self.assertEqual(
            ["runtime.execution.snapshot_verification_failed"],
            [event.event_type for event in collector.events],
        )

    def test_checkpoint_restore_preserves_snapshot_lineage(self):
        node = TaskNode(
            "result",
            NodeType.RESULT,
            "",
            "",
            inputs={"message": literal("ok")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = NativeTaskGraph(
            "graph-checkpoint",
            "goal-checkpoint",
            "conversation",
            nodes=(node,),
            outputs=(GraphOutput("primary", "result", "result", "string"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(CapabilityExecutionAdapter())
        result = executor.execute(graph, snapshot, report)
        checkpoint = executor.checkpoint_store.checkpoints[
            result.session.session_id
        ]
        self.assertEqual(
            CURRENT_SESSION_VERSION,
            checkpoint["sessionVersion"],
        )

        restored = GraphExecutionSession.from_checkpoint(
            checkpoint, graph, snapshot
        )

        self.assertEqual(snapshot.snapshot_id, restored.snapshot_id)
        self.assertEqual(result.session.session_id, restored.session_id)
        self.assertEqual(
            NodeExecutionState.SUCCEEDED,
            restored.node_records["result"].state,
        )
        self.assertEqual(
            result.summary.result_hash, restored.summary.result_hash
        )
        self.assertEqual(result.session.created_at, restored.created_at)
        self.assertEqual(result.session.started_at, restored.started_at)
        self.assertEqual(result.session.completed_at, restored.completed_at)
        self.assertEqual(
            result.session.duration_seconds,
            restored.duration_seconds,
        )
        self.assertEqual(
            ExecutionWaitingReason.NONE,
            restored.waiting_reason,
        )
        self.assertIsNone(restored.waiting_since)

        other_snapshot = replace(snapshot, snapshot_id="different")
        with self.assertRaises(ValueError):
            GraphExecutionSession.from_checkpoint(
                checkpoint, graph, other_snapshot
            )

        legacy_checkpoint = dict(checkpoint)
        legacy_checkpoint.pop("sessionVersion")
        legacy_restored = GraphExecutionSession.from_checkpoint(
            legacy_checkpoint, graph, snapshot
        )
        self.assertEqual(
            CURRENT_SESSION_VERSION,
            legacy_restored.session_version,
        )

        future_checkpoint = dict(checkpoint)
        future_checkpoint["sessionVersion"] = CURRENT_SESSION_VERSION + 1
        with self.assertRaisesRegex(ValueError, "newer"):
            GraphExecutionSession.from_checkpoint(
                future_checkpoint, graph, snapshot
            )

    def test_true_condition_executes_reminder_branch(self):
        weather = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "WeatherReport")},
        )
        condition = TaskNode(
            "condition",
            NodeType.CONDITION,
            "system.condition",
            "condition",
            inputs={
                "value": node_output("weather", "forecast"),
                "expression": literal("rain_probability > 0"),
            },
            outputs={
                "result": OutputDefinition("result", "boolean"),
                "matched_branch": OutputDefinition("matched_branch", "string"),
                "evidence": OutputDefinition("evidence", "ConditionEvidence"),
                "actual_value": OutputDefinition("actual_value", "Any", False),
                "expected_value": OutputDefinition("expected_value", "Any", False),
                "operator": OutputDefinition("operator", "string"),
            },
        )
        reminder = TaskNode(
            "reminder",
            NodeType.CAPABILITY,
            "reminder.create",
            "create",
            inputs={
                "datetime": literal("tomorrowT20:00"),
                "message": literal("우산을 챙기세요."),
                "should_create": node_output("condition", "result", "boolean"),
            },
            outputs={"reminder": OutputDefinition("reminder", "Reminder")},
        )
        result_node = TaskNode(
            "true-result",
            NodeType.RESULT,
            "",
            "",
            inputs={"source": node_output("reminder", "reminder")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = NativeTaskGraph(
            "graph-rain",
            "goal-rain",
            "conversation",
            nodes=(weather, condition, reminder, result_node),
            edges=(
                TaskEdge("weather-condition", "weather", "condition", EdgeType.DATA),
                TaskEdge("condition-reminder", "condition", "reminder", EdgeType.CONDITIONAL_TRUE),
                TaskEdge("reminder-result", "reminder", "true-result", EdgeType.DATA),
            ),
            outputs=(GraphOutput("primary", "true-result", "result", "string"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        calls = []
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "weather.get_forecast": lambda _: {
                        "precipitation_probability": 80
                    },
                    "reminder.create": lambda values: calls.append(values)
                    or {"id": "reminder-1"},
                }
            )
        )

        result = executor.execute(graph, snapshot, report)

        self.assertEqual(GraphExecutionState.SUCCEEDED, result.session.state)
        self.assertEqual(1, len(calls))
        self.assertTrue(calls[0]["should_create"])
        self.assertIn("reminder-1", result.graph_outputs["primary"])

    def test_execution_summary_lists_skips_artifacts_and_permission_wait(self):
        node = TaskNode(
            "create",
            NodeType.CAPABILITY,
            "calendar.create_event",
            "create_event",
            inputs={"title": literal("meeting")},
            outputs={
                "event": OutputDefinition(
                    "event",
                    "CalendarEvent",
                    artifact_type="CalendarEventRef",
                )
            },
            permission_requirement=PermissionRequirement.CONFIRM_REQUIRED,
        )
        graph = NativeTaskGraph(
            "graph-summary-fields",
            "goal-summary-fields",
            "conversation",
            nodes=(node,),
            outputs=(
                GraphOutput(
                    "primary", "create", "event", "CalendarEvent"
                ),
            ),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "calendar.create_event": lambda _: {"id": "event-1"}
                }
            )
        )
        paused = executor.execute(graph, snapshot, report)

        result = executor.execute(
            graph,
            snapshot,
            report,
            confirmed_node_ids=("create",),
            session=paused.session,
        )

        summary = result.summary
        self.assertEqual(result.session.session_id, summary.session_id)
        self.assertEqual(snapshot.snapshot_id, summary.snapshot_id)
        self.assertEqual(("create",), summary.succeeded_nodes)
        self.assertEqual((), summary.skipped_nodes)
        self.assertEqual((), summary.failed_nodes)
        self.assertGreaterEqual(summary.permission_wait_seconds, 0.0)
        self.assertEqual(1, summary.provider_calls)
        self.assertEqual(
            (
                {
                    "nodeId": "create",
                    "outputKey": "event",
                    "artifactType": "CalendarEventRef",
                },
            ),
            summary.artifacts,
        )


if __name__ == "__main__":
    unittest.main()
