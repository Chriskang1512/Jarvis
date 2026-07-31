"""Deterministic baseline planner for supported v1.4 scenarios."""

from __future__ import annotations

import re
from datetime import datetime
from time import perf_counter
from uuid import uuid4

from jarvis.capability_planning.models import (
    Assumption,
    MissingInput,
    PlannerDiagnostics,
    PlannerFailure,
    PlannerFailureReason,
    PlannerResult,
    PlannerStatus,
    PlannerType,
    SuccessCriterionMapping,
)
from jarvis.capability_planning.metadata import PlannerGraphMetadataEnricher
from jarvis.capability_planning.diagnostics import PlannerDiagnosticsSanitizer
from jarvis.capability_planning.validation import CapabilityPlanValidator
from jarvis.native_task_graph import (
    ArtifactPolicy,
    BackoffStrategy,
    BindingSourceType,
    EdgeType,
    GraphExecutionPolicy,
    GraphOutput,
    InputBinding,
    NativeTaskGraph,
    NodeType,
    OutputDefinition,
    PermissionRequirement,
    RetentionPolicy,
    RetryPolicy,
    TaskEdge,
    TaskNode,
    VerificationLevel,
    VerificationPolicy,
)


class RulePlanner:
    PLANNER_VERSION = "deterministic-v1"

    def __init__(self, validator=None):
        self.validator = validator or CapabilityPlanValidator()
        self.metadata_enricher = PlannerGraphMetadataEnricher()

    def plan(self, request):
        started = perf_counter()
        text = request.goal.original_input
        pattern = detect_pattern(text)
        if not pattern:
            return result_without_graph(
                request,
                PlannerStatus.UNSUPPORTED,
                "unsupported_capability",
                started,
            )
        policy_block = blocked_by_policy(pattern, request.planning_policy)
        if policy_block:
            return result_without_graph(
                request,
                PlannerStatus.UNSUPPORTED,
                policy_block,
                started,
            )
        needed = capabilities_for_pattern(pattern)
        missing_capabilities = [
            capability
            for capability in needed
            if request.capability_snapshot.get(capability) is None
        ]
        if missing_capabilities:
            return result_without_graph(
                request,
                PlannerStatus.UNSUPPORTED,
                "unsupported_capability",
                started,
                rejected=tuple(missing_capabilities),
            )
        missing = required_missing_inputs(pattern, request)
        if missing:
            return PlannerResult(
                status=PlannerStatus.NEEDS_USER_INPUT,
                graph=None,
                planner_type=PlannerType.RULE,
                model_id="deterministic-v1",
                capability_snapshot_id=request.capability_snapshot.snapshot_id,
                confidence=1.0,
                missing_inputs=tuple(missing),
                diagnostics=diagnostics(
                    request, started, (), "deterministic_rule_match"
                ),
            )
        graph, mappings = build_pattern_graph(pattern, request)
        graph = self.metadata_enricher.enrich(
            graph,
            request,
            planner_type=PlannerType.RULE,
            planner_version=self.PLANNER_VERSION,
        )
        report = self.validator.validate(
            graph,
            request.capability_snapshot,
            goal=request.goal,
            mappings=mappings,
            max_nodes=request.planning_policy.max_nodes,
        )
        status = PlannerStatus.PLANNED if report.is_valid else PlannerStatus.INVALID
        return PlannerResult(
            status=status,
            graph=graph if report.is_valid else None,
            planner_type=PlannerType.RULE,
            model_id=self.PLANNER_VERSION,
            capability_snapshot_id=request.capability_snapshot.snapshot_id,
            confidence=1.0 if report.is_valid else 0.0,
            assumptions=collect_assumptions(request),
            warnings=tuple(issue.message for issue in report.warnings),
            diagnostics=diagnostics(
                request,
                started,
                tuple(
                    node.capability_id
                    for node in graph.nodes
                    if node.capability_id
                ),
                routing_reason(pattern),
                validation_issues=tuple(issue.code for issue in report.errors),
            ),
            success_criteria_mappings=mappings,
        )


def detect_pattern(text):
    normalized = str(text or "").lower()
    has_condition = any(
        token in normalized
        for token in ("~면", "하면", "오면", "경우", " if ", "when ")
    )
    has_weather = any(
        token in normalized for token in ("비", "날씨", "강수", "rain", "weather")
    )
    has_calendar_update = (
        any(token in normalized for token in ("일정", "calendar"))
        and any(token in normalized for token in ("바꿔", "바꾸", "변경", "update"))
    )
    has_mail = (
        any(token in normalized for token in ("메일", "이메일", "mail", "email"))
        and any(token in normalized for token in ("보내", "전송", "send"))
    )
    if has_condition and has_weather and has_calendar_update and has_mail:
        return "conditional_calendar_update_mail"

    if "비" in text and any(token in text for token in ("오면", "경우")) and any(
        token in text for token in ("알려", "알림", "챙기")
    ):
        return "conditional_reminder"
    if any(token in text for token in ("일정 등록", "약속 등록", "일정 만들어", "일정 추가")):
        return "calendar_create"
    if ("일정" in text or "스케줄" in text) and any(
        token in text for token in ("요약", "정리")
    ):
        return "calendar_summary"
    if "연락처" in text or "주소록" in text:
        return "contacts_search"
    if "날씨" in text or ("비" in text and not "일정" in text):
        return "weather"
    return ""


def capabilities_for_pattern(pattern):
    return {
        "weather": ("weather.get_forecast",),
        "calendar_summary": ("calendar.search_events", "system.format_result"),
        "contacts_search": ("contacts.search",),
        "calendar_create": ("contacts.search", "calendar.create_event"),
        "conditional_reminder": (
            "weather.get_forecast",
            "system.condition",
            "reminder.create",
        ),
        "conditional_calendar_update_mail": (
            "weather.get_forecast",
            "system.condition",
            "calendar.search_events",
            "calendar.update_event",
            "mail.send",
        ),
    }[pattern]


def blocked_by_policy(pattern, policy):
    if pattern in {
        "conditional_reminder",
        "conditional_calendar_update_mail",
    } and not policy.allow_conditions:
        return "conditions_disabled"
    if pattern == "calendar_summary" and not policy.allow_transforms:
        return "transforms_disabled"
    if pattern in {
        "calendar_create",
        "conditional_reminder",
        "conditional_calendar_update_mail",
    } and not policy.allow_external_mutation:
        return "external_mutation_disabled"
    return ""


def required_missing_inputs(pattern, request):
    context = request.semantic_context
    text = request.goal.original_input
    missing = []

    def require(capability, field, value):
        if value in (None, ""):
            missing.append(
                MissingInput(capability, field, f"{field} is required for planning.")
            )

    if pattern in {
        "weather",
        "conditional_reminder",
        "conditional_calendar_update_mail",
    }:
        require("weather.get_forecast", "location", slot(context, "location"))
        require("weather.get_forecast", "date", slot(context, "date") or context.temporal.date)
    if pattern in {"calendar_summary", "calendar_create"}:
        capability = (
            "calendar.search_events"
            if pattern == "calendar_summary"
            else "calendar.create_event"
        )
        require(capability, "date", slot(context, "date") or context.temporal.date)
    if pattern == "contacts_search":
        require("contacts.search", "query", extract_person(text))
    if pattern == "calendar_create":
        require("calendar.create_event", "time", slot(context, "time") or context.temporal.time)
        require("contacts.search", "query", extract_person(text))
        require("calendar.create_event", "title", extract_title(text))
    if pattern == "conditional_reminder":
        require("reminder.create", "datetime", reminder_datetime(request))
        require("reminder.create", "message", reminder_message(text))
    if pattern == "conditional_calendar_update_mail":
        require("calendar.update_event", "title", extract_title(text))
        require(
            "calendar.update_event",
            "time",
            slot(context, "time")
            or context.temporal.time
            or extract_target_time(text),
        )
        require("mail.send", "recipient", extract_person(text))
    return missing


def build_pattern_graph(pattern, request):
    node_specs = capabilities_for_pattern(pattern)
    nodes = []
    edges = []
    context = request.semantic_context
    text = request.goal.original_input
    for index, capability_id in enumerate(node_specs, 1):
        descriptor = request.capability_snapshot.get(capability_id)
        node_id = f"node-{index}-{descriptor.domain}-{descriptor.operation}"
        inputs = rule_inputs(pattern, capability_id, context, text, nodes)
        outputs = {
            item.name: OutputDefinition(
                output_key=item.name,
                value_type=item.value_type,
                is_required=item.is_required,
                artifact_type=item.artifact_type,
                retention_policy=RetentionPolicy.CONVERSATION
                if item.artifact_type
                else RetentionPolicy.TRANSIENT,
            )
            for item in descriptor.output_schema
        }
        verification = verification_for(descriptor)
        nodes.append(
            TaskNode(
                node_id=node_id,
                node_type=node_type_for(capability_id),
                capability_id=capability_id,
                operation=descriptor.operation,
                display_name=descriptor.display_name,
                description=descriptor.description,
                inputs=inputs,
                outputs=outputs,
                required_inputs=tuple(
                    item.name for item in descriptor.input_schema if item.is_required
                ),
                permission_requirement=descriptor.permission_requirement,
                retry_policy=retry_for(descriptor),
                verification_policy=verification,
                metadata={
                    "selectionReason": routing_reason(pattern),
                    "requiresSingleResult": (
                        capability_id == "contacts.search"
                        and pattern == "calendar_create"
                    ),
                },
            )
        )
        if index > 1:
            edge_type = (
                EdgeType.CONDITIONAL_TRUE
                if pattern in {
                    "conditional_reminder",
                    "conditional_calendar_update_mail",
                } and index == 3
                else EdgeType.DATA
            )
            edges.append(
                TaskEdge(
                    f"edge-{index - 1}-{index}",
                    nodes[index - 2].node_id,
                    node_id,
                    edge_type=edge_type,
                    condition="result == true"
                    if edge_type == EdgeType.CONDITIONAL_TRUE
                    else "",
                )
            )
    if pattern in {
        "conditional_reminder",
        "conditional_calendar_update_mail",
    }:
        condition_node = next(
            node
            for node in nodes
            if node.node_type == NodeType.CONDITION
        )
        action_node = nodes[-1]
        action_output = next(iter(action_node.outputs.values()))
        true_result = TaskNode(
            node_id="result-condition-true",
            node_type=NodeType.RESULT,
            capability_id="",
            operation="",
            display_name="Condition matched",
            inputs={
                "source": node_binding(
                    action_node,
                    action_output.output_key,
                    "Any",
                )
            },
            outputs={
                "result": OutputDefinition("result", "string")
            },
            metadata={"matchedBranch": "true"},
        )
        false_result = TaskNode(
            node_id="result-condition-false",
            node_type=NodeType.RESULT,
            capability_id="",
            operation="",
            display_name="Condition not matched",
            inputs={
                "message": literal_binding(
                    "조건이 충족되지 않아 외부 작업을 실행하지 않았습니다.",
                    "string",
                )
            },
            outputs={
                "result": OutputDefinition("result", "string")
            },
            metadata={"matchedBranch": "false"},
        )
        nodes.extend((true_result, false_result))
        edges.extend(
            (
                TaskEdge(
                    "edge-action-true-result",
                    action_node.node_id,
                    true_result.node_id,
                    edge_type=EdgeType.DATA,
                ),
                TaskEdge(
                    "edge-condition-false-result",
                    condition_node.node_id,
                    false_result.node_id,
                    edge_type=EdgeType.CONDITIONAL_FALSE,
                    condition="result == false",
                ),
            )
        )
        graph_outputs = (
            GraphOutput(
                "condition-true-result",
                true_result.node_id,
                "result",
                "string",
                display_name=request.goal.objective,
                is_primary=True,
            ),
            GraphOutput(
                "condition-false-result",
                false_result.node_id,
                "result",
                "string",
                display_name="Condition not matched",
            ),
        )
        mappings = map_success_criteria(
            request, nodes, graph_outputs[0]
        )
        return create_graph(
            request,
            nodes,
            edges,
            graph_outputs,
            mappings,
        ), mappings
    final = nodes[-1]
    final_output = next(iter(final.outputs.values()))
    graph_output = GraphOutput(
        "primary-result",
        final.node_id,
        final_output.output_key,
        final_output.value_type,
        display_name=request.goal.objective,
        is_primary=True,
        artifact_policy=ArtifactPolicy.REFERENCE
        if final_output.artifact_type
        else ArtifactPolicy.NONE,
    )
    mappings = map_success_criteria(request, nodes, graph_output)
    graph = create_graph(
        request,
        nodes,
        edges,
        (graph_output,),
        mappings,
    )
    return graph, mappings


def create_graph(request, nodes, edges, graph_outputs, mappings):
    return NativeTaskGraph(
        graph_id=f"graph-{uuid4()}",
        goal_id=request.goal.goal_id,
        conversation_id=str(
            request.capability_snapshot.environment_constraints.get(
                "conversationId", request.correlation_id or "default"
            )
        ),
        nodes=tuple(nodes),
        edges=tuple(edges),
        outputs=tuple(graph_outputs),
        metadata={
            "capabilitySnapshotId": request.capability_snapshot.snapshot_id,
            "registryHash": request.capability_snapshot.registry_hash,
            "successCriteriaMappings": [
                {
                    "criterionId": item.criterion_id,
                    "nodeId": item.node_id,
                    "outputKey": item.output_key,
                    "verificationLevel": item.verification_level.value,
                }
                for item in mappings
            ],
        },
        execution_policy=GraphExecutionPolicy(
            max_node_count=request.planning_policy.max_nodes
        ),
    )


def rule_inputs(pattern, capability_id, context, text, prior_nodes):
    values = {}
    if capability_id == "weather.get_forecast":
        values["location"] = context_or_literal_binding(
            context, "location", slot(context, "location"), "string"
        )
        values["date"] = context_or_literal_binding(
            context, "date", context.temporal.date, "string"
        )
    elif capability_id == "calendar.search_events":
        values["date"] = context_or_literal_binding(
            context, "date", context.temporal.date, "string"
        )
        if "오후" in text:
            values["time_range"] = literal_binding("afternoon", "string")
    elif capability_id == "contacts.search":
        values["query"] = literal_binding(extract_person(text), "string")
    elif capability_id == "calendar.create_event":
        values["date"] = context_or_literal_binding(
            context, "date", context.temporal.date, "string"
        )
        values["time"] = context_or_literal_binding(
            context, "time", context.temporal.time, "string"
        )
        values["title"] = literal_binding(extract_title(text), "string")
        if prior_nodes:
            source = prior_nodes[-1]
            values["participants"] = node_binding(
                source, "contacts", "ContactList"
            )
    elif capability_id == "system.format_result":
        source = prior_nodes[-1]
        values["source"] = node_binding(source, "events", "CalendarEventList")
    elif capability_id == "system.condition":
        source = prior_nodes[-1]
        values["value"] = node_binding(source, "forecast", "WeatherReport")
        values["expression"] = literal_binding("rain_probability > 0", "string")
    elif capability_id == "reminder.create":
        values["datetime"] = literal_binding(
            f"{context.temporal.date}T{context.temporal.time}", "string"
        )
        values["message"] = literal_binding(reminder_message(text), "string")
        source = prior_nodes[-1]
        values["should_create"] = node_binding(source, "result", "boolean")
    elif capability_id == "calendar.update_event":
        values["date"] = context_or_literal_binding(
            context, "date", context.temporal.date, "string"
        )
        values["title"] = literal_binding(extract_title(text), "string")
        values["time"] = context_or_literal_binding(
            context,
            "time",
            context.temporal.time or extract_target_time(text),
            "string",
        )
        if prior_nodes and prior_nodes[-1].capability_id == "calendar.search_events":
            values["event"] = node_binding(
                prior_nodes[-1], "events", "CalendarEventList"
            )
    elif capability_id == "mail.send":
        values["recipient"] = literal_binding(extract_person(text), "string")
        values["subject"] = literal_binding("일정 변경 안내", "string")
        values["body"] = literal_binding(
            (
                f"{extract_title(text)} 일정이 "
                f"{context.temporal.time or extract_target_time(text)}로 변경되었습니다."
            ),
            "string",
        )
    return values


def context_binding(key, value_type):
    return InputBinding(
        BindingSourceType.CONTEXT_SLOT,
        source_key=key,
        expected_type=value_type,
    )


def context_or_literal_binding(context, key, fallback, value_type):
    return (
        context_binding(key, value_type)
        if key in context.slots
        else literal_binding(fallback, value_type)
    )


def literal_binding(value, value_type):
    return InputBinding(
        BindingSourceType.LITERAL, value=value, expected_type=value_type
    )


def node_binding(node, key, value_type):
    return InputBinding(
        BindingSourceType.NODE_OUTPUT,
        source_node_id=node.node_id,
        source_key=key,
        expected_type=value_type,
    )


def node_type_for(capability_id):
    if capability_id == "system.condition":
        return NodeType.CONDITION
    if capability_id.startswith("system."):
        return NodeType.TRANSFORM
    return NodeType.CAPABILITY


def verification_for(descriptor):
    if descriptor.permission_requirement == PermissionRequirement.CONFIRM_REQUIRED:
        if (
            VerificationLevel.EXTERNAL_READ_BACK
            in descriptor.verification_support.levels
            and descriptor.verification_support.read_back_capability_id
        ):
            return VerificationPolicy(
                VerificationLevel.EXTERNAL_READ_BACK,
                read_back_capability_id=(
                    descriptor.verification_support.read_back_capability_id
                ),
            )
    if descriptor.capability_id in {
        "weather.get_forecast",
        "calendar.search_events",
        "contacts.search",
        "mail.send",
    }:
        return VerificationPolicy(VerificationLevel.SEMANTIC)
    return VerificationPolicy(VerificationLevel.SCHEMA)


def retry_for(descriptor):
    side_effect = str(
        descriptor.execution_characteristics.side_effect or ""
    ).strip().lower()
    safe_read = (
        descriptor.permission_requirement == PermissionRequirement.SAFE
        and side_effect in {"", "none", "read", "readonly", "read_only"}
        and not descriptor.capability_id.startswith("system.")
    )
    if (
        safe_read
        and (
            descriptor.execution_characteristics.network_required
            or descriptor.domain
            in {"weather", "calendar", "contacts", "mail"}
        )
    ):
        return RetryPolicy(
            max_attempts=3,
            delay_seconds=1.0,
            max_delay_seconds=10.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            retryable_categories=(
                "Timeout",
                "RateLimit",
                "TemporaryUnavailable",
                "Network",
                "TransientProviderFailure",
            ),
            jitter=True,
            provider_fallback_allowed=True,
        )
    return RetryPolicy()


def map_success_criteria(request, nodes, graph_output):
    result = []
    for index, criterion in enumerate(request.goal.success_criteria, 1):
        target = select_criterion_node(criterion.description, nodes) or nodes[-1]
        output = next(iter(target.outputs.values()))
        result.append(
            SuccessCriterionMapping(
                criterion.criterion_id,
                target.node_id,
                output.output_key,
                target.verification_policy.verification_level,
            )
        )
    return tuple(result)


def select_criterion_node(description, nodes):
    lowered = description.lower()
    for node in nodes:
        if node.capability_id.split(".")[0] in lowered:
            return node
        if "날씨" in description and node.capability_id.startswith("weather."):
            return node
        if "일정" in description and node.capability_id.startswith("calendar."):
            return node
    return None


def slot(context, key):
    value = context.slots.get(key)
    return value.value if value else ""


def extract_person(text):
    match = re.search(r"([가-힣A-Za-z]{1,20})\s*(?:의)?\s*(?:연락처|와|랑|을|를|만나)", text)
    if not match:
        return ""
    value = match.group(1)
    for prefix in ("내일", "오늘", "오후", "오전"):
        value = value.replace(prefix, "")
    return value.strip()


def extract_title(text):
    person = extract_person(text)
    return f"{person} 만나기" if person else ""


def extract_person_from_semantic_text(text):
    """Extract a named person from a canonical Korean goal."""
    match = re.search(
        r"([가-힣A-Za-z]{1,20})\s*(?:와의|과의|에게|한테|를|을)?\s*"
        r"(?:만나|일정|메일)",
        str(text or ""),
    )
    if not match:
        return ""
    value = match.group(1)
    for prefix in ("내일", "오늘", "오후", "오전", "비가오면", "비오면"):
        value = value.replace(prefix, "")
    return value.strip()


_legacy_extract_person = extract_person
_legacy_extract_title = extract_title


def extract_person(text):
    return extract_person_from_semantic_text(text) or _legacy_extract_person(text)


def extract_title(text):
    if any("가" <= character <= "힣" for character in str(text or "")):
        person = extract_person(text)
        return f"{person} 만나기" if person else ""
    return _legacy_extract_title(text)


def extract_target_time(text):
    raw = str(text or "")
    clean_match = re.search(
        r"(?:(오전|오후)\s*)?(\d{1,2})\s*시",
        raw,
    )
    period = ""
    if clean_match:
        period = str(clean_match.group(1) or "")
        hour = int(clean_match.group(2))
    else:
        korean_hours = {
            "한": 1,
            "두": 2,
            "세": 3,
            "네": 4,
            "다섯": 5,
            "여섯": 6,
            "일곱": 7,
            "여덟": 8,
            "아홉": 9,
            "열": 10,
            "열한": 11,
            "열두": 12,
        }
        word_match = re.search(
            r"(?:(오전|오후)\s*)?"
            r"(열두|열한|다섯|여섯|일곱|여덟|아홉|한|두|세|네|열)\s*시",
            raw,
        )
        if word_match:
            period = str(word_match.group(1) or "")
            hour = korean_hours[word_match.group(2)]
        else:
            hour = None
    if hour is not None:
        if not 1 <= hour <= 12:
            return ""
        if period == "오후" and hour < 12:
            hour += 12
        if period == "오전" and hour == 12:
            hour = 0
        return f"{hour:02d}:00:00"

    match = re.search(r"(?:오후|오전)?\s*(\d{1,2})\s*시", str(text or ""))
    if not match:
        return ""
    hour = int(match.group(1))
    if "오후" in match.group(0) and hour < 12:
        hour += 12
    if "오전" in match.group(0) and hour == 12:
        hour = 0
    return f"{hour:02d}:00:00"


def reminder_message(text):
    match = re.search(r"(.+?)(?:라고)?\s*(?:알려|알림)", text)
    value = match.group(1) if match else ""
    value = re.sub(r"^.*?(?:오면|경우)\s*", "", value).strip()
    value = re.sub(r"^(?:오전|오후)?\s*\d+시(?:에)?\s*", "", value).strip()
    return value


def reminder_datetime(request):
    temporal = request.semantic_context.temporal
    return (
        f"{temporal.date}T{temporal.time}"
        if temporal.date and temporal.time
        else ""
    )


def routing_reason(pattern):
    return {
        "weather": "deterministic_rule_match",
        "contacts_search": "deterministic_rule_match",
        "calendar_summary": "multi_capability_dependency",
        "calendar_create": "external_mutation",
        "conditional_reminder": "conditional_goal",
        "conditional_calendar_update_mail": "conditional_goal",
    }.get(pattern, "deterministic_rule_match")


def diagnostics(
    request,
    started,
    selected,
    reason,
    rejected=(),
    validation_issues=(),
):
    input_length, input_hash = (
        PlannerDiagnosticsSanitizer.input_fingerprint(
            request.goal.original_input
        )
    )
    return PlannerDiagnostics(
        planner_type=PlannerType.RULE.value,
        planner_duration_ms=int((perf_counter() - started) * 1000),
        selected_capabilities=tuple(selected),
        rejected_capabilities=tuple(rejected),
        validation_issues=tuple(validation_issues),
        capability_snapshot_id=request.capability_snapshot.snapshot_id,
        registry_hash=request.capability_snapshot.registry_hash,
        routing_reason=reason,
        confidence=1.0,
        input_length=input_length,
        input_hash=input_hash,
        entity_summary=PlannerDiagnosticsSanitizer.entity_summary(
            request.semantic_context
        ),
    )


def result_without_graph(request, status, reason, started, rejected=()):
    rejected = tuple(rejected)
    failure_reason = (
        PlannerFailureReason.UNSUPPORTED_CONDITIONAL
        if "condition" in reason or "system.condition" in rejected
        else PlannerFailureReason.POLICY_BLOCKED
        if reason.endswith("_disabled")
        else PlannerFailureReason.UNSUPPORTED_CAPABILITY
    )
    return PlannerResult(
        status=status,
        graph=None,
        planner_type=PlannerType.RULE,
        model_id="deterministic-v1",
        capability_snapshot_id=request.capability_snapshot.snapshot_id,
        confidence=0.0,
        diagnostics=diagnostics(
            request, started, (), reason, rejected=rejected
        ),
        failure=PlannerFailure(
            reason=failure_reason,
            missing_capabilities=rejected,
            missing_nodes=("ConditionNode",)
            if failure_reason == PlannerFailureReason.UNSUPPORTED_CONDITIONAL
            else (),
            suggested_capabilities=rejected,
            recoverable=bool(rejected)
            or failure_reason == PlannerFailureReason.UNSUPPORTED_CONDITIONAL,
        ),
    )


def collect_assumptions(request):
    assumptions = []
    for name, semantic_slot in request.semantic_context.slots.items():
        source = semantic_slot.provenance.source.name
        if source not in {"USER_PREFERENCE", "SYSTEM_DEFAULT"}:
            continue
        assumptions.append(
            Assumption(
                field=name,
                assumed_value=semantic_slot.value,
                reason="Planner reused a configured context value.",
                confidence=semantic_slot.confidence,
                source=source,
            )
        )
    return tuple(assumptions)
