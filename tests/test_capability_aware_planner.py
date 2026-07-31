import json
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from jarvis.abilities.operations import CapabilityOperationMetadata
from jarvis.capability_planning import (
    AIPlanner,
    CapabilityDescriptor,
    CapabilityInputDefinition,
    CapabilityOutputDefinition,
    CapabilityPlanValidator,
    CapabilityRegistryAdapter,
    CapabilityRegistrySnapshot,
    ExecutionPlanShadowComparer,
    ExecutionPlanSnapshot,
    ExecutionPlanSnapshotFactory,
    SnapshotVerifier,
    HybridPlanner,
    NativePlanningCoordinator,
    PlannerDiagnosticsSanitizer,
    PlannerRequest,
    PlannerFailureReason,
    PlannerStatus,
    PlanningPolicy,
    RulePlanner,
    planner_result_from_json,
    planner_result_to_json,
    snapshot_from_json,
    snapshot_to_json,
    link_semantic_replan,
)
from jarvis.capability_planning.rule_planner import extract_target_time
from jarvis.goals import (
    GoalSpecification,
    SemanticContext,
    SemanticSlot,
    SuccessCriterion,
    TemporalContext,
)
from jarvis.native_task_graph import (
    BindingSourceType,
    GraphOutput,
    InputBinding,
    NativeTaskGraph,
    NativeTaskGraphSerializer,
    NodeType,
    OutputDefinition,
    PermissionRequirement,
    TaskNode,
)
from jarvis.voice import VoicePipeline
from jarvis.debug_trace import format_trace_event


NOW = datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc)


class FakeRegistry:
    def __init__(self, operations):
        self.operations = operations

    def list_operations(self):
        return list(self.operations)


class QueueProvider:
    def __init__(self, replies, delay=0):
        self.replies = list(replies)
        self.delay = delay

    def generate(self, prompt):
        if self.delay:
            time.sleep(self.delay)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def metadata(self):
        return SimpleNamespace(model="test-model")


class LegacyDispatcherMustNotRun:
    def create_plan(self, text):
        raise AssertionError("goal-oriented request reached legacy planner")


def operation(capability, action, permission="safe", availability="ONLINE"):
    return CapabilityOperationMetadata(
        capability=capability,
        operation=action,
        permission=permission,
        availability=availability,
        health_reason="NONE" if availability == "ONLINE" else "UNKNOWN",
    )


def standard_snapshot():
    operations = [
        operation("weather", "query"),
        operation("calendar", "list"),
        operation("calendar", "create", "confirm_required"),
        operation("calendar", "update", "confirm_required"),
        operation("contacts", "get"),
        operation("mail", "send", "confirm_required"),
        operation("reminder", "create", "confirm_required"),
    ]
    return CapabilityRegistryAdapter().create_snapshot(
        FakeRegistry(operations),
        environment_constraints={"conversationId": "conversation-test"},
    )


def goal(text, domain, *, location="", date="2026-07-29", time_value=""):
    slots = {}
    if location:
        slots["location"] = SemanticSlot("location", location)
    if date:
        slots["date"] = SemanticSlot("date", date)
    if time_value:
        slots["time"] = SemanticSlot("time", time_value)
    context = SemanticContext(
        domain=domain,
        slots=slots,
        temporal=TemporalContext(
            reference_date="2026-07-28",
            date=date,
            time=time_value,
        ),
        confidence=0.95,
    )
    specification = GoalSpecification(
        goal_id="goal-test",
        original_input=text,
        objective=text,
        success_criteria=(SuccessCriterion(f"{domain} 완료"),),
        context=context,
        confidence=0.95,
        created_at=NOW.isoformat(),
    )
    return specification


def request(specification, snapshot=None, policy=None):
    return PlannerRequest(
        goal=specification,
        semantic_context=specification.context,
        capability_snapshot=snapshot or standard_snapshot(),
        planning_policy=policy or PlanningPolicy(),
        correlation_id="correlation-test",
    )


def planned(specification):
    return RulePlanner().plan(request(specification))


class TestCapabilityAwarePlanner(unittest.TestCase):
    def test_01_capability_descriptor_creation(self):
        descriptor = CapabilityDescriptor(
            "example.read",
            "1.0",
            "Read",
            "Read example",
            "example",
            "read",
            input_schema=(CapabilityInputDefinition("id", "string", True),),
            output_schema=(CapabilityOutputDefinition("result", "string"),),
        )
        self.assertEqual("example.read", descriptor.capability_id)

    def test_02_existing_ability_operation_adapter(self):
        descriptor = CapabilityRegistryAdapter().from_operation(
            operation("weather", "query")
        )
        self.assertEqual("weather.get_forecast", descriptor.capability_id)
        self.assertEqual("forecast", descriptor.output_schema[0].name)

    def test_03_snapshot_is_immutable(self):
        snapshot = standard_snapshot()
        with self.assertRaises(TypeError):
            snapshot.environment_constraints["x"] = 1
        with self.assertRaises(AttributeError):
            snapshot.capabilities.append("x")

    def test_04_registry_hash_is_stable(self):
        first = standard_snapshot()
        second = standard_snapshot()
        self.assertEqual(first.registry_hash, second.registry_hash)

    def test_05_weather_graph(self):
        result = planned(goal("내일 강릉 날씨 알려줘", "weather", location="강릉"))
        self.assertEqual(PlannerStatus.PLANNED, result.status)
        self.assertEqual(
            ("weather.get_forecast",),
            tuple(node.capability_id for node in result.graph.nodes),
        )

    def test_06_calendar_search_summary_graph(self):
        result = planned(goal("내일 오후 일정 찾아서 요약해줘", "calendar"))
        self.assertEqual(
            ("calendar.search_events", "system.format_result"),
            tuple(node.capability_id for node in result.graph.nodes),
        )

    def test_07_contacts_search_graph(self):
        result = planned(goal("아야 연락처 찾아줘", "contacts", date=""))
        self.assertEqual("contacts.search", result.graph.nodes[0].capability_id)

    def test_08_calendar_create_permission(self):
        result = planned(
            goal(
                "내일 오후 3시에 아야 만나는 일정 등록해줘",
                "calendar",
                time_value="15:00:00",
            )
        )
        create = result.graph.nodes[-1]
        self.assertEqual("calendar.create_event", create.capability_id)
        self.assertEqual(
            PermissionRequirement.CONFIRM_REQUIRED,
            create.permission_requirement,
        )

    def test_09_conditional_reminder_graph(self):
        result = planned(
            goal(
                "내일 비가 오면 오후 8시에 우산 챙기라고 알려줘",
                "reminder",
                location="서울",
                time_value="20:00:00",
            )
        )
        self.assertEqual(
            (
                "weather.get_forecast",
                "system.condition",
                "reminder.create",
            ),
            tuple(
                node.capability_id
                for node in result.graph.nodes
                if node.capability_id
            ),
        )
        self.assertIn(
            "ConditionalTrue",
            {edge.edge_type.value for edge in result.graph.edges},
        )

    def test_10_node_output_binding_is_connected(self):
        result = planned(goal("내일 오후 일정 찾아서 요약해줘", "calendar"))
        binding = result.graph.nodes[1].inputs["source"]
        self.assertEqual(BindingSourceType.NODE_OUTPUT, binding.source_type)
        self.assertEqual(result.graph.nodes[0].node_id, binding.source_node_id)

    def test_11_unregistered_capability_is_blocked(self):
        graph = simple_graph("invented.fly", "fly")
        report = CapabilityPlanValidator().validate(graph, standard_snapshot())
        self.assertIn("UNREGISTERED_CAPABILITY", issue_codes(report))

    def test_12_capability_input_type_error(self):
        snapshot = standard_snapshot()
        descriptor = snapshot.get("weather.get_forecast")
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            descriptor.capability_id,
            descriptor.operation,
            inputs={
                "location": InputBinding(
                    BindingSourceType.LITERAL,
                    value=42,
                    expected_type="integer",
                ),
                "date": InputBinding(
                    BindingSourceType.LITERAL,
                    value="2026-07-29",
                    expected_type="string",
                ),
            },
            outputs={"forecast": OutputDefinition("forecast", "WeatherReport")},
        )
        graph = graph_with_node(node, "forecast", "WeatherReport")
        report = CapabilityPlanValidator().validate(graph, snapshot)
        self.assertIn("CAPABILITY_INPUT_TYPE_MISMATCH", issue_codes(report))

    def test_13_missing_required_input_needs_user_input(self):
        result = planned(goal("내일 날씨 알려줘", "weather", location=""))
        self.assertEqual(PlannerStatus.NEEDS_USER_INPUT, result.status)
        self.assertEqual("location", result.missing_inputs[0].field)

    def test_14_permission_downgrade_is_blocked(self):
        snapshot = standard_snapshot()
        descriptor = snapshot.get("calendar.create_event")
        node = TaskNode(
            "create",
            NodeType.CAPABILITY,
            descriptor.capability_id,
            descriptor.operation,
            permission_requirement=PermissionRequirement.SAFE,
        )
        report = CapabilityPlanValidator().validate(
            NativeTaskGraph("g", "goal", "conversation", nodes=(node,)),
            snapshot,
        )
        self.assertIn("PERMISSION_DOWNGRADE", issue_codes(report))

    def test_15_success_criteria_mapping(self):
        result = planned(goal("내일 강릉 날씨 알려줘", "weather", location="강릉"))
        self.assertEqual(1, len(result.success_criteria_mappings))
        self.assertEqual(
            result.graph.nodes[0].node_id,
            result.success_criteria_mappings[0].node_id,
        )

    def test_16_hybrid_selects_rule_first(self):
        ai = AIPlanner(QueueProvider([RuntimeError("must not run")]))
        result = HybridPlanner(ai_planner=ai).plan(
            request(goal("내일 강릉 날씨 알려줘", "weather", location="강릉"))
        )
        self.assertEqual("RulePlanner", result.planner_type.value)

    def test_17_ai_structured_output(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        graph = valid_ai_graph(specification, standard_snapshot())
        result = AIPlanner(
            QueueProvider([NativeTaskGraphSerializer.to_json(graph)])
        ).plan(request(specification))
        self.assertEqual(PlannerStatus.PLANNED, result.status)

    def test_18_ai_failure_safe_fallback(self):
        specification = goal("알 수 없는 복합 작업", "general", date="")
        result = HybridPlanner(
            ai_planner=AIPlanner(QueueProvider([RuntimeError("offline")]))
        ).plan(request(specification))
        self.assertEqual(PlannerStatus.FAILED, result.status)
        self.assertIsNone(result.graph)

    def test_19_invalid_graph_repair_once(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        invalid = simple_graph("invented.fly", "fly")
        valid = replace(
            valid_ai_graph(specification, standard_snapshot()),
            version=2,
        )
        provider = QueueProvider(
            [
                NativeTaskGraphSerializer.to_json(invalid),
                NativeTaskGraphSerializer.to_json(valid),
            ]
        )
        result = HybridPlanner(ai_planner=AIPlanner(provider)).plan(
            request(specification)
        )
        self.assertEqual(PlannerStatus.PLANNED, result.status)
        self.assertEqual(1, result.diagnostics.repair_count)

    def test_20_repair_limit_exceeded(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        invalid = NativeTaskGraphSerializer.to_json(
            simple_graph("invented.fly", "fly")
        )
        result = HybridPlanner(
            ai_planner=AIPlanner(QueueProvider([invalid, invalid, invalid]))
        ).plan(
            request(
                specification,
                policy=PlanningPolicy(max_repair_attempts=2),
            )
        )
        self.assertEqual(PlannerStatus.FAILED, result.status)
        self.assertEqual(2, result.diagnostics.repair_count)

    def test_21_planner_timeout(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        graph = valid_ai_graph(specification, standard_snapshot())
        result = AIPlanner(
            QueueProvider([NativeTaskGraphSerializer.to_json(graph)], delay=0.02)
        ).plan(
            request(
                specification,
                policy=PlanningPolicy(planner_timeout_seconds=0.001),
            )
        )
        self.assertEqual(PlannerStatus.FAILED, result.status)
        self.assertEqual("planner_timeout", result.diagnostics.ai_failure)

    def test_22_max_node_count_blocked(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        graph = valid_ai_graph(specification, standard_snapshot())
        result = AIPlanner(
            QueueProvider([NativeTaskGraphSerializer.to_json(graph)])
        ).plan(request(specification, policy=PlanningPolicy(max_nodes=0)))
        self.assertEqual(PlannerStatus.INVALID, result.status)

    def test_23_provider_specific_capability_rejected(self):
        with self.assertRaisesRegex(ValueError, "provider"):
            CapabilityDescriptor(
                "google_calendar.create_event",
                "1",
                "bad",
                "bad",
                "google_calendar",
                "create_event",
            )

    def test_24_shadow_comparison_equivalent(self):
        result = planned(goal("내일 강릉 날씨 알려줘", "weather", location="강릉"))
        legacy = SimpleNamespace(
            steps=(
                SimpleNamespace(
                    tool_name="weather", action="query", permission="safe"
                ),
            )
        )
        comparison = ExecutionPlanShadowComparer().compare(legacy, result.graph)
        self.assertTrue(comparison.is_equivalent)

    def test_25_shadow_comparison_difference(self):
        result = planned(goal("내일 강릉 날씨 알려줘", "weather", location="강릉"))
        legacy = SimpleNamespace(
            steps=(SimpleNamespace(tool_name="contacts", action="get", permission="safe"),)
        )
        comparison = ExecutionPlanShadowComparer().compare(legacy, result.graph)
        self.assertFalse(comparison.is_equivalent)
        self.assertTrue(comparison.differences)

    def test_26_planner_result_json(self):
        result = planned(goal("내일 강릉 날씨 알려줘", "weather", location="강릉"))
        restored = planner_result_from_json(planner_result_to_json(result))
        self.assertEqual(result.status, restored.status)
        self.assertEqual(
            NativeTaskGraphSerializer.to_dict(result.graph),
            NativeTaskGraphSerializer.to_dict(restored.graph),
        )

    def test_27_snapshot_json(self):
        snapshot = standard_snapshot()
        restored = snapshot_from_json(snapshot_to_json(snapshot))
        self.assertEqual(snapshot.registry_hash, restored.registry_hash)
        self.assertEqual(
            tuple(item.capability_id for item in snapshot.capabilities),
            tuple(item.capability_id for item in restored.capabilities),
        )

    def test_28_direct_execution_contract_untouched(self):
        from jarvis.runtime.intent import IntentContext, RuleIntentParser

        result = RuleIntentParser().parse(
            "내일 일정 알려줘",
            IntentContext(current_date="2026-07-28", current_time="10:00:00"),
        )
        self.assertTrue(result.success)

    def test_29_conditional_calendar_update_and_mail_graph(self):
        specification = goal(
            "내일 비가 오면 아야 만나기 일정을 오후 4시로 바꾸고 "
            "아야에게 메일을 보내",
            "calendar",
            location="서울",
            time_value="16:00:00",
        )

        result = planned(specification)

        self.assertEqual(PlannerStatus.PLANNED, result.status)
        self.assertEqual(
            (
                "weather.get_forecast",
                "system.condition",
                "calendar.search_events",
                "calendar.update_event",
                "mail.send",
            ),
            tuple(
                node.capability_id
                for node in result.graph.nodes
                if node.capability_id
            ),
        )
        self.assertEqual(
            "ConditionalTrue",
            result.graph.edges[1].edge_type.value,
        )
        self.assertEqual(
            PermissionRequirement.CONFIRM_REQUIRED,
            result.graph.nodes[3].permission_requirement,
        )
        self.assertEqual(
            PermissionRequirement.CONFIRM_REQUIRED,
            result.graph.nodes[4].permission_requirement,
        )
        event_binding = result.graph.nodes[3].inputs["event"]
        self.assertEqual(BindingSourceType.NODE_OUTPUT, event_binding.source_type)
        self.assertEqual(
            result.graph.nodes[2].node_id,
            event_binding.source_node_id,
        )

    def test_30_missing_condition_capability_has_structured_failure(self):
        specification = goal(
            "내일 비가 오면 아야 만나기 일정을 오후 4시로 바꾸고 "
            "아야에게 메일을 보내",
            "calendar",
            location="서울",
            time_value="16:00:00",
        )
        snapshot = standard_snapshot()
        without_condition = CapabilityRegistrySnapshot.create(
            tuple(
                item
                for item in snapshot.capabilities
                if item.capability_id != "system.condition"
            ),
            environment_constraints=snapshot.environment_constraints,
        )

        result = RulePlanner().plan(request(specification, snapshot=without_condition))

        self.assertEqual(PlannerStatus.UNSUPPORTED, result.status)
        self.assertEqual(
            PlannerFailureReason.UNSUPPORTED_CONDITIONAL,
            result.failure.reason,
        )
        self.assertEqual(
            ("system.condition",),
            result.failure.missing_capabilities,
        )
        self.assertEqual(("ConditionNode",), result.failure.missing_nodes)
        self.assertTrue(result.failure.recoverable)

    def test_31_planner_failure_json_round_trip(self):
        specification = goal(
            "내일 비가 오면 아야 만나기 일정을 오후 4시로 바꾸고 "
            "아야에게 메일을 보내",
            "calendar",
            location="서울",
            time_value="16:00:00",
        )
        snapshot = standard_snapshot()
        without_condition = CapabilityRegistrySnapshot.create(
            tuple(
                item
                for item in snapshot.capabilities
                if item.capability_id != "system.condition"
            )
        )
        result = RulePlanner().plan(request(specification, snapshot=without_condition))

        restored = planner_result_from_json(planner_result_to_json(result))

        self.assertEqual(result.failure, restored.failure)

    def test_32_voice_goal_route_plans_before_legacy_dispatcher(self):
        coordinator = NativePlanningCoordinator(
            standard_snapshot(),
            planner=HybridPlanner(),
            user_preferences={"location": "서울"},
            native_execution_enabled=False,
        )
        runtime = SimpleNamespace(
            tool_dispatcher=LegacyDispatcherMustNotRun()
        )
        pipeline = VoicePipeline(
            None,
            None,
            None,
            None,
            intent_runtime=runtime,
            native_planning_coordinator=coordinator,
        )

        result = pipeline.try_intent_runtime(
            "내일 비가 오면 아야 만나기 일정을 오후 4시로 바꾸고 "
            "아야한테 메일도 보내"
        )

        self.assertTrue(result.handled)
        self.assertEqual("native_execution_disabled", result.error)
        self.assertEqual("native_task_graph", result.tool)
        self.assertEqual("planned_not_executed", result.status)
        self.assertTrue(result.graph_id)
        self.assertIsNotNone(result.execution_plan_snapshot)
        self.assertEqual(
            result.graph_id,
            result.plan.graph_id,
        )
        self.assertNotIn("unsupported_conditional", result.response)
        self.assertEqual(
            (
                "weather.get_forecast",
                "system.condition",
                "calendar.search_events",
                "calendar.update_event",
                "mail.send",
            ),
            tuple(
                node.capability_id
                for node in result.plan.nodes
                if node.capability_id
            ),
        )

    def test_33_voice_direct_route_still_uses_legacy_dispatcher(self):
        direct_plan = SimpleNamespace(
            requires_clarification=False,
            intent_error="",
            unsupported_reason="",
            steps=(),
        )
        dispatcher = SimpleNamespace(create_plan=lambda text: direct_plan)
        runtime = SimpleNamespace(
            tool_dispatcher=dispatcher,
            create_context=lambda text, **kwargs: text,
            run=lambda context, **kwargs: SimpleNamespace(
                handled=False,
                context=context,
            ),
        )
        coordinator = NativePlanningCoordinator(
            standard_snapshot(),
            planner=HybridPlanner(),
            user_preferences={"location": "서울"},
        )
        pipeline = VoicePipeline(
            None,
            None,
            None,
            None,
            intent_runtime=runtime,
            native_planning_coordinator=coordinator,
        )

        result = pipeline.try_intent_runtime("오늘 날씨 알려줘")

        self.assertFalse(result.handled)

    def test_34_single_supported_mutation_stays_on_legacy_route(self):
        coordinator = NativePlanningCoordinator(
            standard_snapshot(),
            planner=HybridPlanner(),
            user_preferences={"location": "서울"},
        )

        outcome = coordinator.plan(
            "내일 오후 3시에 아야 만나기 일정을 등록해",
            conversation_id="conversation-test",
            session_id="session-test",
        )

        self.assertIsNone(outcome)

    def test_35_native_graph_is_deeply_immutable(self):
        metadata = {"nested": {"items": ["original"]}}
        binding_value = {"time": "16:00", "items": [1]}
        node = TaskNode(
            "immutable",
            NodeType.RESULT,
            "",
            "",
            inputs={
                "value": InputBinding(
                    BindingSourceType.LITERAL,
                    value=binding_value,
                    expected_type="Any",
                )
            },
            outputs={"result": OutputDefinition("result", "string")},
            metadata=metadata,
        )
        graph = NativeTaskGraph(
            "immutable-graph",
            "goal-test",
            "conversation-test",
            nodes=(node,),
            metadata=metadata,
        )

        metadata["nested"]["items"].append("changed")
        binding_value["time"] = "17:00"
        binding_value["items"].append(2)

        self.assertEqual(
            ("original",),
            graph.metadata["nested"]["items"],
        )
        self.assertEqual("16:00", node.inputs["value"].value["time"])
        self.assertEqual((1,), node.inputs["value"].value["items"])
        with self.assertRaises(TypeError):
            graph.metadata["nested"]["new"] = True

    def test_36_frozen_graph_serializes_to_mutable_projection(self):
        graph = NativeTaskGraph(
            "projection",
            "goal-test",
            "conversation-test",
            metadata={"nested": {"items": ["one", "two"]}},
            created_at=NOW,
            updated_at=NOW,
        )

        projected = NativeTaskGraphSerializer.to_dict(graph)

        self.assertIsInstance(projected["metadata"]["nested"], dict)
        self.assertIsInstance(projected["metadata"]["nested"]["items"], list)

    def test_37_rule_graph_has_reproducibility_metadata(self):
        result = planned(
            goal("내일 강릉 날씨 알려줘", "weather", location="강릉")
        )

        self.assertEqual(
            {
                "capabilitySnapshotId",
                "registryHash",
                "plannerType",
                "plannerVersion",
                "planningPolicyVersion",
            },
            {
                key
                for key in result.graph.metadata
                if key
                in {
                    "capabilitySnapshotId",
                    "registryHash",
                    "plannerType",
                    "plannerVersion",
                    "planningPolicyVersion",
                }
            },
        )
        self.assertEqual(
            result.capability_snapshot_id,
            result.graph.metadata["capabilitySnapshotId"],
        )

    def test_38_ai_metadata_is_overwritten_by_runtime(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        graph = valid_ai_graph(specification, standard_snapshot())
        graph = replace(
            graph,
            metadata={
                **dict(graph.metadata),
                "registryHash": "untrusted",
                "plannerType": "invented",
            },
        )

        result = AIPlanner(
            QueueProvider([NativeTaskGraphSerializer.to_json(graph)]),
            model_id="test-ai-v1",
        ).plan(request(specification))

        self.assertEqual(PlannerStatus.PLANNED, result.status)
        self.assertEqual("AIPlanner", result.graph.metadata["plannerType"])
        self.assertEqual("test-ai-v1", result.graph.metadata["plannerVersion"])
        self.assertEqual(
            standard_snapshot().registry_hash,
            result.graph.metadata["registryHash"],
        )

    def test_39_condition_contract_and_both_branches(self):
        result = planned(
            goal(
                "내일 비가 오면 아야 만나기 일정을 오후 4시로 바꾸고 "
                "아야에게 메일을 보내",
                "calendar",
                location="서울",
                time_value="16:00:00",
            )
        )
        condition = next(
            node
            for node in result.graph.nodes
            if node.capability_id == "system.condition"
        )

        self.assertEqual(
            {
                "result",
                "matched_branch",
                "evidence",
                "actual_value",
                "expected_value",
                "operator",
            },
            set(condition.outputs),
        )
        edge_types = {
            edge.edge_type.value
            for edge in result.graph.edges
            if edge.source_node_id == condition.node_id
        }
        self.assertIn("ConditionalTrue", edge_types)
        self.assertIn("ConditionalFalse", edge_types)
        false_target = next(
            edge.target_node_id
            for edge in result.graph.edges
            if edge.source_node_id == condition.node_id
            and edge.edge_type.value == "ConditionalFalse"
        )
        false_node = result.graph.node(false_target)
        self.assertEqual(NodeType.RESULT, false_node.node_type)
        self.assertEqual("false", false_node.metadata["matchedBranch"])

    def test_40_success_criterion_id_is_preserved(self):
        specification = goal(
            "내일 강릉 날씨 알려줘",
            "weather",
            location="강릉",
        )
        result = planned(specification)

        self.assertEqual(
            specification.success_criteria[0].criterion_id,
            result.success_criteria_mappings[0].criterion_id,
        )

    def test_41_wrong_repair_version_is_blocked(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        original = simple_graph("invented.fly", "fly")
        wrong = valid_ai_graph(specification, standard_snapshot())
        planner = AIPlanner(
            QueueProvider([NativeTaskGraphSerializer.to_json(wrong)])
        )

        with self.assertRaisesRegex(ValueError, "version"):
            planner.repair(
                request(specification),
                original,
                SimpleNamespace(errors=()),
                1,
            )

    def test_42_diagnostics_sanitizer_masks_sensitive_values(self):
        raw = (
            "email=aya@example.com phone=010-1234-5678 "
            "path=C:\\Users\\aya\\secret.txt "
            "Authorization=Bearer abc123 API_KEY=secret "
            "title=아야 일정 body=민감한 메일 본문"
        )

        sanitized = PlannerDiagnosticsSanitizer.sanitize_text(raw)

        self.assertIn("[REDACTED_EMAIL]", sanitized)
        self.assertIn("[REDACTED_PHONE]", sanitized)
        self.assertIn("[REDACTED_PATH]", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)
        self.assertNotIn("아야 일정", sanitized)
        self.assertNotIn("민감한 메일 본문", sanitized)

    def test_43_diagnostics_do_not_store_raw_input_or_entity_value(self):
        specification = goal(
            "내일 비가 오면 아야에게 메일을 보내",
            "mail",
            location="서울",
            time_value="16:00:00",
        )
        result = RulePlanner().plan(request(specification))
        serialized = json.dumps(
            json.loads(planner_result_to_json(result))["diagnostics"],
            ensure_ascii=False,
        )

        self.assertNotIn(specification.original_input, serialized)
        self.assertNotIn("아야", serialized)

    def test_44_wrong_repair_graph_id_is_blocked(self):
        specification = goal("지원되는 복합 작업", "general", date="")
        original = simple_graph("invented.fly", "fly")
        wrong = replace(
            valid_ai_graph(specification, standard_snapshot()),
            graph_id="different-graph",
            version=2,
        )
        planner = AIPlanner(
            QueueProvider([NativeTaskGraphSerializer.to_json(wrong)])
        )

        with self.assertRaisesRegex(ValueError, "GraphId"):
            planner.repair(
                request(specification),
                original,
                SimpleNamespace(errors=()),
                1,
            )

    def test_45_semantic_replan_uses_new_id_and_lineage(self):
        original = simple_graph("invented.fly", "fly")
        replanned = replace(
            original,
            graph_id="graph-replanned",
            version=1,
        )

        linked = link_semantic_replan(original, replanned)

        self.assertEqual("graph-replanned", linked.graph_id)
        self.assertEqual(original.graph_id, linked.metadata["parentGraphId"])
        self.assertEqual(
            original.version,
            linked.metadata["previousGraphVersion"],
        )
        with self.assertRaisesRegex(ValueError, "new GraphId"):
            link_semantic_replan(original, original)

    def test_46_planning_diagnostics_labels_are_unambiguous(self):
        intent = format_trace_event(
            "intent.rule",
            {"matched": False, "confidence": 0.95},
        )
        route = format_trace_event(
            "runtime.goal_router.routed",
            {
                "request_route": "goal_oriented",
                "routing_reasons": ["conditional_branch"],
            },
        )
        planner = format_trace_event(
            "runtime.native_planner.completed",
            {
                "planner_type": "RulePlanner",
                "planner_status": "Planned",
                "graph_id": "graph-1",
                "graph_node_count": 7,
                "validation_status": "Valid",
                "selected_capabilities": ["system.condition"],
            },
        )

        self.assertIn(
            "[Intent Parser] parser_source=rule intent_match=false",
            intent,
        )
        self.assertIn(
            "[Goal Router] request_route=goal_oriented",
            route,
        )
        self.assertIn(
            "[TaskGraph Planner] planner_type=RulePlanner "
            "planner_status=Planned",
            planner,
        )

    def test_47_execution_plan_snapshot_contains_only_audit_identity(self):
        specification = goal(
            "내일 강릉 날씨 알려줘",
            "weather",
            location="강릉",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        snapshot = ExecutionPlanSnapshotFactory(
            CapabilityPlanValidator()
        ).create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
            max_nodes=planner_request.planning_policy.max_nodes,
        )

        self.assertEqual(
            {
                "graphHash",
                "plannerMetadata",
                "planningConfidence",
                "snapshotId",
                "validationHash",
                "createdAt",
            },
            set(snapshot.to_dict()),
        )
        self.assertEqual(
            result.graph.metadata["plannerVersion"],
            snapshot.planner_metadata["plannerVersion"],
        )
        self.assertEqual(result.confidence, snapshot.planning_confidence)
        with self.assertRaises(TypeError):
            snapshot.planner_metadata["plannerType"] = "changed"

    def test_48_execution_plan_hashes_are_stable(self):
        specification = goal(
            "내일 강릉 날씨 알려줘",
            "weather",
            location="강릉",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        factory = ExecutionPlanSnapshotFactory(
            CapabilityPlanValidator()
        )

        first = factory.create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        second = factory.create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )

        self.assertEqual(first.graph_hash, second.graph_hash)
        self.assertEqual(first.validation_hash, second.validation_hash)
        self.assertNotEqual(first.snapshot_id, second.snapshot_id)

    def test_49_graph_tampering_changes_execution_snapshot_hash(self):
        specification = goal(
            "내일 강릉 날씨 알려줘",
            "weather",
            location="강릉",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        factory = ExecutionPlanSnapshotFactory(
            CapabilityPlanValidator()
        )
        original = factory.create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        changed_graph = replace(
            result.graph,
            version=result.graph.version + 1,
        )
        changed_result = replace(result, graph=changed_graph)
        changed = factory.create(
            changed_result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )

        self.assertNotEqual(original.graph_hash, changed.graph_hash)

    def test_50_execution_plan_snapshot_round_trip(self):
        specification = goal(
            "내일 강릉 날씨 알려줘",
            "weather",
            location="강릉",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        snapshot = ExecutionPlanSnapshotFactory(
            CapabilityPlanValidator()
        ).create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )

        restored = ExecutionPlanSnapshot.from_dict(snapshot.to_dict())

        self.assertEqual(snapshot, restored)

    def test_51_snapshot_verifier_accepts_intact_plan(self):
        specification = goal(
            "내일 강릉 날씨 알려줘.",
            "weather",
            location="媛뺣쫱",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        validator = CapabilityPlanValidator()
        report = validator.validate(
            result.graph,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        snapshot = ExecutionPlanSnapshotFactory(validator).create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )

        verification = SnapshotVerifier().verify(
            snapshot, result.graph, report
        )

        self.assertTrue(verification.is_valid)
        self.assertEqual((), verification.issues)

    def test_52_snapshot_verifier_rejects_graph_tampering(self):
        specification = goal(
            "내일 강릉 날씨 알려줘.",
            "weather",
            location="媛뺣쫱",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        validator = CapabilityPlanValidator()
        report = validator.validate(
            result.graph,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        snapshot = ExecutionPlanSnapshotFactory(validator).create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        changed_graph = replace(
            result.graph, version=result.graph.version + 1
        )

        verification = SnapshotVerifier().verify(
            snapshot, changed_graph, report
        )

        self.assertFalse(verification.is_valid)
        self.assertIn(
            "graph_hash_mismatch",
            {issue.code for issue in verification.issues},
        )

    def test_53_snapshot_verifier_rejects_validation_tampering(self):
        specification = goal(
            "내일 강릉 날씨 알려줘.",
            "weather",
            location="媛뺣쫱",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        validator = CapabilityPlanValidator()
        report = validator.validate(
            result.graph,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        snapshot = ExecutionPlanSnapshotFactory(validator).create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        changed_report = replace(report, graph_id="different-graph")

        verification = SnapshotVerifier().verify(
            snapshot, result.graph, changed_report
        )

        self.assertFalse(verification.is_valid)
        self.assertIn(
            "validation_hash_mismatch",
            {issue.code for issue in verification.issues},
        )

    def test_54_snapshot_verifier_rejects_unsupported_versions(self):
        specification = goal(
            "내일 강릉 날씨 알려줘.",
            "weather",
            location="媛뺣쫱",
        )
        planner_request = request(specification)
        result = RulePlanner().plan(planner_request)
        validator = CapabilityPlanValidator()
        report = validator.validate(
            result.graph,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )
        snapshot = ExecutionPlanSnapshotFactory(validator).create(
            result,
            planner_request.capability_snapshot,
            goal=specification,
            mappings=result.success_criteria_mappings,
        )

        verification = SnapshotVerifier().verify(
            snapshot,
            result.graph,
            report,
            snapshot_version="2.0",
            schema_version="2.0",
        )

        self.assertFalse(verification.is_valid)
        self.assertEqual(
            {
                "snapshot_version_unsupported",
                "schema_version_unsupported",
            },
            {issue.code for issue in verification.issues},
        )

    def test_55_native_execution_feature_flag_invokes_executor(self):
        calls = []
        execution_result = SimpleNamespace(
            session=SimpleNamespace(
                state=SimpleNamespace(value="Succeeded")
            ),
            graph_outputs={"primary": "done"},
            requires_permission=False,
            error="",
        )

        class RecordingExecutor:
            def execute(self, graph, snapshot, report, **kwargs):
                calls.append((graph, snapshot, report, kwargs))
                return execution_result

        specification = goal(
            "\ub0b4\uc77c \uac15\ub989 \ub0a0\uc528 \uc54c\ub824\uc918.",
            "weather",
            location="媛뺣쫱",
        )
        capability_snapshot = standard_snapshot()
        rule_planner = RulePlanner()
        planned_result = rule_planner.plan(
            request(specification, snapshot=capability_snapshot)
        )

        class FixedGoalParser:
            def parse(self, *args, **kwargs):
                return SimpleNamespace(
                    goal=specification,
                    route="goal_oriented",
                    routing_reasons=("multiple_capabilities",),
                )

        class FixedPlanner:
            validator = rule_planner.validator

            def plan(self, planner_request):
                return planned_result

        coordinator = NativePlanningCoordinator(
            capability_snapshot,
            planner=FixedPlanner(),
            goal_parser=FixedGoalParser(),
            native_execution_enabled=True,
            graph_executor=RecordingExecutor(),
        )

        outcome = coordinator.plan(
            specification.original_input,
            conversation_id="conversation-test",
            session_id="session-test",
        )

        self.assertIsNotNone(outcome)
        self.assertEqual(1, len(calls))
        self.assertIs(execution_result, outcome.execution_result)
        self.assertEqual(
            outcome.execution_plan_snapshot.snapshot_id,
            calls[0][1].snapshot_id,
        )
        self.assertTrue(calls[0][2].is_valid)

    def test_56_target_time_parses_korean_digit_and_word_hours(self):
        self.assertEqual(
            "16:00:00",
            extract_target_time("일정을 오후 4시로 변경해줘"),
        )
        self.assertEqual(
            "04:00:00",
            extract_target_time("일정을 네시로 변경해줘"),
        )


def issue_codes(report):
    return {item.code for item in report.errors}


def simple_graph(capability_id, operation_name):
    node = TaskNode(
        "node",
        NodeType.CAPABILITY,
        capability_id,
        operation_name,
        outputs={"result": OutputDefinition("result", "string")},
    )
    return graph_with_node(node, "result", "string")


def graph_with_node(node, output_key, output_type):
    return NativeTaskGraph(
        "graph-ai",
        "goal-test",
        "conversation-test",
        nodes=(node,),
        outputs=(
            GraphOutput(
                "primary", node.node_id, output_key, output_type, is_primary=True
            ),
        ),
        metadata={"successCriteriaMappings": []},
        created_at=NOW,
        updated_at=NOW,
    )


def valid_ai_graph(specification, snapshot):
    descriptor = snapshot.get("system.format_result")
    node = TaskNode(
        "format",
        NodeType.TRANSFORM,
        descriptor.capability_id,
        descriptor.operation,
        inputs={
            "source": InputBinding(
                BindingSourceType.LITERAL,
                value="safe",
                expected_type="Any",
            )
        },
        outputs={"result": OutputDefinition("result", "string")},
        required_inputs=("source",),
        permission_requirement=descriptor.permission_requirement,
    )
    return NativeTaskGraph(
        "graph-ai",
        specification.goal_id,
        "conversation-test",
        nodes=(node,),
        outputs=(
            GraphOutput("primary", "format", "result", "string", is_primary=True),
        ),
        metadata={
            "successCriteriaMappings": [
                {
                    "criterionId": specification.success_criteria[0].criterion_id,
                    "nodeId": "format",
                    "outputKey": "result",
                    "verificationLevel": "Schema",
                }
            ]
        },
        created_at=NOW,
        updated_at=NOW,
    )


if __name__ == "__main__":
    unittest.main()
