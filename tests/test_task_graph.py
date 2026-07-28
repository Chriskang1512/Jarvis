import unittest

from jarvis.debug_trace import subscribe_trace, unsubscribe_trace
from jarvis.input import InputManager, InputModality, InputSource
from jarvis.permissions import PermissionDecision, PermissionLevel, PermissionStatus
from jarvis.runtime import BusyPolicy, RuntimeTurnLock, TurnOwner, TurnPriority
from jarvis.runtime.task import (
    AbilitySemanticContract,
    ArtifactRef,
    GraphState,
    GraphValidationCode,
    GraphValidationStage,
    InputBinding,
    InMemoryTaskGraphCheckpointStore,
    InvalidTaskGraph,
    NodeState,
    RetryPolicy,
    SemanticValidationCode,
    SemanticRegistry,
    SemanticType,
    TaskGraph,
    TaskGraphCoordinator,
    TaskGraphValidator,
    TaskGraphSemanticValidator,
    TaskGraphCapabilityValidator,
    TaskGraphPermissionValidator,
    TaskGraphStructuralValidator,
    TaskNode,
    TurnResult,
    TurnResultStatus,
    ExecutionPlanAdapter,
)
from jarvis.runtime.planner import ExecutionPlan, ExecutionStep


def travel_graph():
    return TaskGraph(
        graph_id="GRAPH-OSAKA",
        task_id="RT-42",
        goal="오사카 여행 계획",
        nodes=(
            TaskNode("search", "search"),
            TaskNode("translate", "translate", dependencies=("search",)),
            TaskNode("calendar", "calendar", dependencies=("translate",)),
            TaskNode("mail", "mail", dependencies=("calendar",)),
        ),
    )


class TestTaskGraph(unittest.TestCase):
    def test_execution_plan_adapter_preserves_order_and_input_equivalence(self):
        plan = ExecutionPlan(
            raw_text="오늘 강릉 날씨",
            id="RP-SHADOW",
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="weather",
                    action="query",
                    input_data={"location": "강릉"},
                ),
                ExecutionStep(
                    index=2,
                    tool_name="mail",
                    action="draft",
                    input_data={"subject": "날씨"},
                    depends_on=(1,),
                ),
            ),
        )

        graph = ExecutionPlanAdapter().to_task_graph(plan)
        comparison = ExecutionPlanAdapter().compare(plan, graph)

        self.assertTrue(comparison.equivalent)
        self.assertEqual(graph.graph_id, "GRAPH-RP-SHADOW")
        self.assertEqual(graph.nodes[1].dependencies, ("STEP-1-WEATHER",))
        self.assertEqual(graph.nodes[0].operation, "query")
        self.assertEqual(graph.nodes[0].output_types["result"], "WeatherReport")
        self.assertNotIn("강릉", repr(comparison.to_dict()))

    def test_dag_exposes_only_dependency_satisfied_nodes(self):
        graph = travel_graph()

        self.assertEqual([node.node_id for node in graph.ready_nodes()], ["search"])

    def test_missing_dependency_is_rejected(self):
        with self.assertRaisesRegex(InvalidTaskGraph, "Unknown dependencies"):
            TaskGraph(
                graph_id="GRAPH-BAD",
                task_id="RT-BAD",
                goal="bad",
                nodes=(TaskNode("mail", "mail", dependencies=("calendar",)),),
            )

    def test_cycle_is_rejected(self):
        with self.assertRaisesRegex(InvalidTaskGraph, "acyclic"):
            TaskGraph(
                graph_id="GRAPH-CYCLE",
                task_id="RT-CYCLE",
                goal="cycle",
                nodes=(
                    TaskNode("a", "search", dependencies=("b",)),
                    TaskNode("b", "mail", dependencies=("a",)),
                ),
            )

    def test_completed_result_unlocks_next_node_and_preserves_artifacts(self):
        store = InMemoryTaskGraphCheckpointStore()
        coordinator = TaskGraphCoordinator(store)
        graph = coordinator.start(travel_graph())
        graph = coordinator.refresh_ready(graph)
        before = store.load(graph.graph_id)
        artifact = ArtifactRef(
            artifact_id="ART-1",
            artifact_type="search_result",
            uri="memory://search/1",
            fingerprint="abc",
        )

        graph = coordinator.record_result(
            graph,
            TurnResult(
                turn_id="TURN-000284",
                task_id="RT-42",
                node_id="search",
                status=TurnResultStatus.COMPLETED,
                output={"summary": "오사카 검색 결과"},
                artifact_refs=(artifact,),
                memory_refs=("MEM-1",),
            ),
        )
        graph = coordinator.refresh_ready(graph)

        search = graph.node("search")
        self.assertEqual(search.state, NodeState.COMPLETED)
        self.assertEqual(search.turn_ids, ("TURN-000284",))
        self.assertEqual(search.artifact_refs, (artifact,))
        self.assertEqual(search.memory_refs, ("MEM-1",))
        self.assertEqual(graph.node("translate").state, NodeState.READY)
        self.assertNotEqual(store.load(graph.graph_id).fingerprint, before.fingerprint)
        self.assertEqual(
            coordinator.result_store.load("TURN-000284").output,
            {"summary": "오사카 검색 결과"},
        )
        self.assertEqual(
            coordinator.result_store.for_node("RT-42", "search")[0].artifact_refs,
            (artifact,),
        )

    def test_failed_node_retries_with_a_new_turn_then_fails(self):
        coordinator = TaskGraphCoordinator()
        graph = TaskGraph(
            graph_id="GRAPH-RETRY",
            task_id="RT-RETRY",
            goal="retry",
            nodes=(
                TaskNode(
                    "search",
                    "search",
                    retry_policy=RetryPolicy(max_attempts=2),
                ),
            ),
        )
        first = TurnResult(
            "TURN-1",
            "RT-RETRY",
            "search",
            TurnResultStatus.FAILED,
            error="offline",
        )
        second = TurnResult(
            "TURN-2",
            "RT-RETRY",
            "search",
            TurnResultStatus.TIMEOUT,
            error="timeout",
        )

        graph = coordinator.record_result(graph, first)
        self.assertEqual(graph.node("search").state, NodeState.RETRYING)
        graph = coordinator.record_result(graph, second)

        self.assertEqual(graph.node("search").state, NodeState.FAILED)
        self.assertEqual(graph.node("search").turn_ids, ("TURN-1", "TURN-2"))
        self.assertEqual(graph.state, GraphState.FAILED)

    def test_checkpoint_revision_advances_for_every_graph_mutation(self):
        store = InMemoryTaskGraphCheckpointStore()
        coordinator = TaskGraphCoordinator(store)
        graph = coordinator.start(travel_graph())
        first_revision = graph.revision
        graph = coordinator.refresh_ready(graph)

        checkpoint = store.load(graph.graph_id)

        self.assertEqual(first_revision, 1)
        self.assertEqual(graph.revision, 2)
        self.assertEqual(checkpoint.revision, 2)
        self.assertEqual(len(checkpoint.fingerprint), 64)
        self.assertIs(checkpoint.graph, graph)

    def test_ready_node_maps_to_runtime_turn_task_and_step(self):
        coordinator = TaskGraphCoordinator()
        graph = coordinator.refresh_ready(travel_graph())
        lock = RuntimeTurnLock()

        lease = coordinator.acquire_node_turn(
            graph,
            "search",
            lock,
            owner=TurnOwner.PLUGIN,
            policy=BusyPolicy.QUEUE,
            priority=TurnPriority.PLUGIN,
        )

        self.assertEqual(lease.turn.task_id, "RT-42")
        self.assertEqual(lease.turn.step_id, "search")
        self.assertEqual(lease.turn.source, "task_graph")
        self.assertEqual(lease.graph.node("search").state, NodeState.RUNNING)
        self.assertEqual(
            coordinator.checkpoint_store.load(graph.graph_id).graph.node("search").state,
            NodeState.RUNNING,
        )
        lock.release(lease.turn)

    def test_non_ready_node_cannot_create_turn(self):
        graph = travel_graph()

        with self.assertRaisesRegex(InvalidTaskGraph, "not ready"):
            TaskGraphCoordinator().acquire_node_turn(
                graph,
                "mail",
                RuntimeTurnLock(),
            )

    def test_result_for_another_task_is_rejected(self):
        result = TurnResult(
            "TURN-X",
            "RT-OTHER",
            "search",
            TurnResultStatus.COMPLETED,
        )

        with self.assertRaisesRegex(InvalidTaskGraph, "task_id"):
            TaskGraphCoordinator().record_result(travel_graph(), result)

    def test_completed_node_output_flows_into_downstream_input(self):
        coordinator = TaskGraphCoordinator()
        graph = TaskGraph(
            graph_id="GRAPH-DATA",
            task_id="RT-DATA",
            goal="translate hotels",
            nodes=(
                TaskNode("search", "search"),
                TaskNode(
                    "translate",
                    "translate",
                    dependencies=("search",),
                    input={"language": "ja"},
                    input_bindings=(
                        InputBinding("hotels", "search", "hotels"),
                    ),
                    required_inputs=("hotels", "language"),
                ),
            ),
        )
        graph = coordinator.record_result(
            graph,
            TurnResult(
                "TURN-SEARCH",
                "RT-DATA",
                "search",
                TurnResultStatus.COMPLETED,
                output={"hotels": ["A", "B"]},
            ),
        )
        graph = coordinator.refresh_ready(graph)

        resolved = coordinator.resolve_node_input(graph, "translate")

        self.assertEqual(resolved, {"language": "ja", "hotels": ["A", "B"]})

    def test_node_turn_lease_contains_materialized_input(self):
        coordinator = TaskGraphCoordinator()
        graph = TaskGraph(
            graph_id="GRAPH-LEASE-DATA",
            task_id="RT-LEASE-DATA",
            goal="search",
            nodes=(TaskNode("search", "search", input={"city": "Osaka"}),),
        )
        graph = coordinator.refresh_ready(graph)
        lock = RuntimeTurnLock()

        lease = coordinator.acquire_node_turn(graph, "search", lock)

        self.assertEqual(lease.input_data, {"city": "Osaka"})
        lock.release(lease.turn)

    def test_missing_runtime_output_is_rejected_before_lock_acquisition(self):
        coordinator = TaskGraphCoordinator()
        graph = TaskGraph(
            graph_id="GRAPH-MISSING-OUTPUT",
            task_id="RT-MISSING-OUTPUT",
            goal="translate",
            nodes=(
                TaskNode(
                    "search",
                    "search",
                    state=NodeState.COMPLETED,
                    output={},
                ),
                TaskNode(
                    "translate",
                    "translate",
                    dependencies=("search",),
                    state=NodeState.READY,
                    input_bindings=(InputBinding("hotels", "search", "hotels"),),
                ),
            ),
        )
        lock = RuntimeTurnLock()

        with self.assertRaisesRegex(InvalidTaskGraph, "Missing input"):
            coordinator.acquire_node_turn(graph, "translate", lock)

        self.assertIsNone(lock.current_turn)

    def test_input_binding_source_must_be_dependency(self):
        with self.assertRaisesRegex(InvalidTaskGraph, "must be a dependency"):
            TaskGraph(
                graph_id="GRAPH-BINDING",
                task_id="RT-BINDING",
                goal="bad binding",
                nodes=(
                    TaskNode("search", "search"),
                    TaskNode(
                        "translate",
                        "translate",
                        input_bindings=(InputBinding("items", "search"),),
                    ),
                ),
            )

    def test_validator_rejects_missing_input_and_ability(self):
        graph = TaskGraph(
            graph_id="GRAPH-VALIDATE",
            task_id="RT-VALIDATE",
            goal="validate",
            nodes=(
                TaskNode(
                    "pdf",
                    "pdf.create",
                    required_inputs=("document",),
                ),
            ),
        )
        validator = TaskGraphValidator(ability_registry={})

        report = validator.validate(graph)

        self.assertFalse(report.valid)
        self.assertEqual(
            {issue.code for issue in report.issues},
            {
                GraphValidationCode.MISSING_INPUT,
                GraphValidationCode.ABILITY_UNAVAILABLE,
            },
        )

    def test_validator_checks_provider_capability_and_permission(self):
        graph = TaskGraph(
            graph_id="GRAPH-CAPABILITY",
            task_id="RT-CAPABILITY",
            goal="create pdf",
            nodes=(
                TaskNode(
                    "pdf",
                    "creator",
                    input={"document": "content"},
                    required_inputs=("document",),
                    provider_capability="pdf.generate",
                ),
            ),
        )
        validator = TaskGraphValidator(
            ability_registry={"creator": object()},
            provider_checker=lambda capability, node, ability: False,
            permission_checker=lambda node, ability: False,
        )

        report = validator.validate(graph)

        self.assertEqual(
            {issue.code for issue in report.issues},
            {
                GraphValidationCode.PROVIDER_UNAVAILABLE,
                GraphValidationCode.PERMISSION_DENIED,
            },
        )

    def test_coordinator_refuses_to_start_invalid_validated_graph(self):
        graph = TaskGraph(
            graph_id="GRAPH-START-VALIDATION",
            task_id="RT-START-VALIDATION",
            goal="unavailable",
            nodes=(TaskNode("pdf", "pdf.create"),),
        )
        coordinator = TaskGraphCoordinator(
            validator=TaskGraphValidator(ability_registry={})
        )

        with self.assertRaisesRegex(InvalidTaskGraph, "Ability is unavailable"):
            coordinator.start(graph)

    def test_semantic_validator_rejects_wrong_upstream_output_type(self):
        graph = TaskGraph(
            graph_id="GRAPH-SEMANTIC",
            task_id="RT-SEMANTIC",
            goal="book translated hotel",
            nodes=(
                TaskNode(
                    "translate",
                    "translate",
                    output_types={"$": "weather_report"},
                ),
                TaskNode(
                    "book",
                    "hotel.book",
                    dependencies=("translate",),
                    input_bindings=(InputBinding("hotel", "translate"),),
                    input_types={"hotel": "hotel_record"},
                ),
            ),
        )

        report = TaskGraphSemanticValidator().validate(graph)

        self.assertFalse(report.valid)
        self.assertEqual(
            report.issues[0].code,
            SemanticValidationCode.INPUT_TYPE_MISMATCH,
        )

    def test_semantic_validator_checks_ability_contract(self):
        graph = TaskGraph(
            graph_id="GRAPH-ABILITY-SEMANTIC",
            task_id="RT-ABILITY-SEMANTIC",
            goal="translate",
            nodes=(
                TaskNode(
                    "translate",
                    "translate",
                    input_types={"text": "weather_report"},
                    output_types={"$": "translated_text"},
                ),
            ),
        )
        validator = TaskGraphSemanticValidator(
            contracts={
                "translate": AbilitySemanticContract(
                    "translate",
                    input_types={"text": "hotel_list"},
                    output_types={"$": "translated_text"},
                )
            }
        )

        report = validator.validate(graph)

        self.assertEqual(
            [issue.code for issue in report.issues],
            [SemanticValidationCode.INPUT_TYPE_MISMATCH],
        )

    def test_structural_and_semantic_validation_run_before_start(self):
        semantic = TaskGraphSemanticValidator(
            semantic_checker=lambda graph: "Plan intent does not match the goal."
        )
        graph = TaskGraph(
            graph_id="GRAPH-SEMANTIC-START",
            task_id="RT-SEMANTIC-START",
            goal="hotel",
            nodes=(TaskNode("search", "search"),),
        )
        coordinator = TaskGraphCoordinator(
            validator=TaskGraphValidator(semantic_validator=semantic)
        )

        with self.assertRaisesRegex(InvalidTaskGraph, "does not match"):
            coordinator.start(graph)

    def test_keyboard_envelope_binds_to_node_input(self):
        envelope = InputManager().create(
            InputSource.KEYBOARD,
            InputModality.TEXT,
            content="오사카 호텔을 찾아줘",
        )
        graph = TaskGraph(
            graph_id="GRAPH-KEYBOARD",
            task_id="RT-KEYBOARD",
            goal="hotel search",
            nodes=(
                TaskNode(
                    "planner",
                    "planner",
                    input_bindings=(
                        InputBinding(
                            "request",
                            accepted_sources=("keyboard",),
                            accepted_modalities=("text",),
                        ),
                    ),
                    required_inputs=("request",),
                ),
            ),
        )

        resolved = TaskGraphCoordinator().resolve_node_input(
            graph,
            "planner",
            input_envelopes=(envelope,),
        )

        self.assertEqual(resolved["request"], "오사카 호텔을 찾아줘")

    def test_image_ocr_and_voice_can_use_same_envelope_binding_contract(self):
        manager = InputManager()
        graph = TaskGraph(
            graph_id="GRAPH-MULTI-INPUT",
            task_id="RT-MULTI-INPUT",
            goal="normalize input",
            nodes=(
                TaskNode(
                    "planner",
                    "planner",
                    input_bindings=(InputBinding("request"),),
                ),
            ),
        )
        coordinator = TaskGraphCoordinator()

        for source, modality, content in (
            (InputSource.VOICE, InputModality.TEXT, "음성 전사"),
            (InputSource.OCR, InputModality.TEXT, "OCR 결과"),
            (InputSource.IMAGE, InputModality.IMAGE, {"image_id": "IMG-1"}),
        ):
            envelope = manager.create(source, modality, content=content)
            resolved = coordinator.resolve_node_input(
                graph,
                "planner",
                input_envelopes=(envelope,),
            )
            self.assertEqual(resolved["request"], content)

    def test_semantic_registry_resolves_alias_and_parent_compatibility(self):
        registry = SemanticRegistry(
            (
                SemanticType("Any"),
                SemanticType("Text", parents=("Any",)),
                SemanticType("WeatherReport", parents=("Text",), aliases=("weather",)),
            )
        )

        self.assertEqual(registry.canonical_name("weather"), "WeatherReport")
        self.assertTrue(registry.compatible("WeatherReport", "Text"))
        self.assertFalse(registry.compatible("Text", "WeatherReport"))

    def test_semantic_validator_rejects_unregistered_type(self):
        graph = TaskGraph(
            graph_id="GRAPH-UNKNOWN-TYPE",
            task_id="RT-UNKNOWN-TYPE",
            goal="unknown",
            nodes=(
                TaskNode(
                    "search",
                    "search",
                    output_types={"$": "ImaginaryHotelWeather"},
                ),
            ),
        )

        report = TaskGraphSemanticValidator().validate(graph)

        self.assertEqual(
            report.issues[0].code,
            SemanticValidationCode.UNKNOWN_SEMANTIC_TYPE,
        )
        self.assertEqual(report.issues[0].stage, GraphValidationStage.SEMANTIC)

    def test_validation_pipeline_reports_explicit_stage_order(self):
        graph = TaskGraph(
            graph_id="GRAPH-STAGES",
            task_id="RT-STAGES",
            goal="pdf",
            nodes=(
                TaskNode(
                    "pdf",
                    "pdf.create",
                    provider_capability="pdf.generate",
                ),
            ),
        )
        validator = TaskGraphValidator(
            structural_validator=TaskGraphStructuralValidator(),
            semantic_validator=TaskGraphSemanticValidator(),
            capability_validator=TaskGraphCapabilityValidator(
                ability_registry={},
            ),
            permission_validator=TaskGraphPermissionValidator(
                permission_checker=lambda node, ability: False,
            ),
        )

        report = validator.validate(graph)

        self.assertEqual(
            [issue.stage for issue in report.issues],
            [GraphValidationStage.CAPABILITY, GraphValidationStage.PERMISSION],
        )

    def test_validation_report_serializes_all_dashboard_stages(self):
        graph = TaskGraph(
            graph_id="GRAPH-DASHBOARD-REPORT",
            task_id="RT-DASHBOARD-REPORT",
            goal="delete",
            nodes=(TaskNode("delete", "DeleteFile"),),
        )
        report = TaskGraphValidator(
            permission_checker=lambda node, ability: False,
        ).validate(graph)

        payload = report.to_dict()

        self.assertEqual(
            [stage["stage"] for stage in payload["stages"]],
            ["STRUCTURAL", "SEMANTIC", "CAPABILITY", "PERMISSION"],
        )
        self.assertEqual(payload["stages"][-1]["status"], "FAIL")
        self.assertTrue(
            all(
                isinstance(stage["duration_ms"], float)
                and stage["duration_ms"] >= 0
                for stage in payload["stages"]
            )
        )

    def test_permission_validation_exposes_debugger_details(self):
        graph = TaskGraph(
            graph_id="GRAPH-PERMISSION-DETAIL",
            task_id="RT-PERMISSION-DETAIL",
            goal="delete calendar event",
            nodes=(TaskNode("DeleteCalendarNode", "Calendar Delete"),),
        )
        report = TaskGraphValidator(
            permission_checker=lambda node, ability: PermissionDecision(
                PermissionStatus.DENIED,
                PermissionLevel.RESTRICTED,
                "Confirm Required",
            )
        ).validate(graph)

        issue = report.to_dict()["stages"][-1]["issues"][0]

        self.assertEqual(issue["details"]["reason"], "Confirm Required")
        self.assertEqual(issue["details"]["ability"], "Calendar Delete")
        self.assertEqual(issue["details"]["risk"], "restricted")
        self.assertEqual(issue["node_id"], "DeleteCalendarNode")
        self.assertEqual(issue["code"], "PERMISSION_DENIED")

    def test_graph_correlated_tts_event_is_explicit(self):
        observations = []
        observer = lambda event, payload: observations.append((event, payload))
        subscribe_trace(observer)
        try:
            graph = travel_graph()
            returned = TaskGraphCoordinator().record_tts(
                graph,
                "completed",
                provider="openai",
                latency_ms=284,
            )
        finally:
            unsubscribe_trace(observer)

        event, payload = observations[-1]
        self.assertIs(returned, graph)
        self.assertEqual(event, "runtime.task_graph.tts")
        self.assertEqual(payload["graph_id"], "GRAPH-OSAKA")
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
