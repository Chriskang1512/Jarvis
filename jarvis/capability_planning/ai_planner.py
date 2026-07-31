"""Structured-output AI planner and bounded validation repair support."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import replace
from time import perf_counter

from jarvis.capability_planning.models import (
    MissingInput,
    PlannerDiagnostics,
    PlannerResult,
    PlannerStatus,
    PlannerType,
)
from jarvis.capability_planning.metadata import (
    PlannerGraphMetadataEnricher,
    enforce_validation_repair_version,
)
from jarvis.capability_planning.diagnostics import PlannerDiagnosticsSanitizer
from jarvis.capability_planning.validation import CapabilityPlanValidator
from jarvis.native_task_graph import NativeTaskGraphSerializer


class AIPlanner:
    def __init__(self, provider=None, *, model_id="", validator=None):
        self.provider = provider
        self.model_id = model_id
        self.validator = validator or CapabilityPlanValidator()
        self.metadata_enricher = PlannerGraphMetadataEnricher()

    def plan(self, request):
        started = perf_counter()
        if self.provider is None:
            return failed_result(request, "AI planner is unavailable.", started)
        try:
            try:
                reply = generate_with_timeout(
                    self.provider,
                    create_planner_prompt(request),
                    request.planning_policy.planner_timeout_seconds,
                )
            except FutureTimeout:
                return failed_result(request, "planner_timeout", started)
            graph = parse_graph_reply(reply)
            graph = apply_registry_permissions(graph, request.capability_snapshot)
            planner_version = (
                self.model_id or provider_model(self.provider) or "ai-planner-v1"
            )
            graph = self.metadata_enricher.enrich(
                graph,
                request,
                planner_type=PlannerType.AI,
                planner_version=planner_version,
            )
            mappings = mappings_from_graph(graph)
            report = self.validator.validate(
                graph,
                request.capability_snapshot,
                goal=request.goal,
                mappings=mappings,
                max_nodes=request.planning_policy.max_nodes,
            )
            missing_issues = [
                issue
                for issue in report.errors
                if issue.code
                in {
                    "CAPABILITY_REQUIRED_INPUT_MISSING",
                    "REQUIRED_INPUT_MISSING",
                }
            ]
            if missing_issues:
                return PlannerResult(
                    status=PlannerStatus.NEEDS_USER_INPUT,
                    graph=None,
                    planner_type=PlannerType.AI,
                    model_id=self.model_id or provider_model(self.provider),
                    capability_snapshot_id=request.capability_snapshot.snapshot_id,
                    confidence=0.0,
                    missing_inputs=tuple(
                        MissingInput(
                            capability_id=next(
                                (
                                    node.capability_id
                                    for node in graph.nodes
                                    if node.node_id == issue.node_id
                                ),
                                "",
                            ),
                            field=issue.field_path.rsplit(".", 1)[-1],
                            reason=issue.message,
                        )
                        for issue in missing_issues
                    ),
                    diagnostics=ai_diagnostics(
                        request,
                        started,
                        graph,
                        validation_issues=tuple(
                            issue.code for issue in report.errors
                        ),
                    ),
                )
            return PlannerResult(
                status=PlannerStatus.PLANNED
                if report.is_valid
                else PlannerStatus.INVALID,
                graph=graph,
                planner_type=PlannerType.AI,
                model_id=self.model_id or provider_model(self.provider),
                capability_snapshot_id=request.capability_snapshot.snapshot_id,
                confidence=0.85 if report.is_valid else 0.0,
                diagnostics=ai_diagnostics(
                    request,
                    started,
                    graph,
                    validation_issues=tuple(
                        issue.code for issue in report.errors
                    ),
                ),
                success_criteria_mappings=mappings,
            )
        except Exception as error:
            return failed_result(request, str(error), started)

    def repair(self, request, invalid_graph, report, attempt):
        if self.provider is None:
            return None
        reply = self.provider.generate(
            create_repair_prompt(request, invalid_graph, report, attempt)
        )
        graph = parse_graph_reply(reply)
        graph = apply_registry_permissions(
            graph, request.capability_snapshot
        )
        graph = enforce_validation_repair_version(invalid_graph, graph)
        return self.metadata_enricher.enrich(
            graph,
            request,
            planner_type=PlannerType.AI,
            planner_version=(
                self.model_id or provider_model(self.provider) or "ai-planner-v1"
            ),
        )


def create_planner_prompt(request):
    from jarvis.capability_planning.serialization import snapshot_to_dict

    return json.dumps(
        {
            "task": "Create one NativeTaskGraph JSON object only. Do not execute.",
            "goal": request.goal.to_dict(),
            "semanticContext": request.semantic_context.to_dict(),
            "capabilitySnapshot": snapshot_to_dict(request.capability_snapshot),
            "planningPolicy": {
                "maxNodes": request.planning_policy.max_nodes,
                "allowConditions": request.planning_policy.allow_conditions,
                "allowTransforms": request.planning_policy.allow_transforms,
                "allowUserConfirmation": request.planning_policy.allow_user_confirmation,
                "allowExternalMutation": request.planning_policy.allow_external_mutation,
                "allowPreviousResult": request.planning_policy.allow_previous_result,
                "parallelExecution": False,
            },
            "schema": {
                "schemaVersion": "1.0",
                "required": [
                    "graphId",
                    "goalId",
                    "conversationId",
                    "nodes",
                    "edges",
                    "outputs",
                    "executionPolicy",
                    "createdAt",
                    "updatedAt",
                ],
            },
            "forbidden": [
                "capability not in snapshot",
                "provider-specific capability id",
                "permission downgrade",
                "free-form explanation",
                "invented required input",
                "execution state",
            ],
            "example": {
                "binding": {
                    "sourceType": "ContextSlot",
                    "sourceKey": "location",
                    "expectedType": "string",
                    "isRequired": True,
                }
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def create_repair_prompt(request, graph, report, attempt):
    return json.dumps(
        {
            "task": "Repair only the listed validation issues. Return graph JSON only.",
            "attempt": attempt,
            "originalGoal": request.goal.to_dict(),
            "invalidGraph": NativeTaskGraphSerializer.to_dict(graph),
            "validationIssues": [
                {
                    "code": issue.code,
                    "nodeId": issue.node_id,
                    "fieldPath": issue.field_path,
                    "suggestedFix": issue.suggested_fix,
                }
                for issue in report.errors
            ],
            "capabilitySnapshotId": request.capability_snapshot.snapshot_id,
            "allowedCapabilities": [
                item.capability_id
                for item in request.capability_snapshot.capabilities
            ],
            "rule": "Do not alter goal meaning.",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def parse_graph_reply(reply):
    if isinstance(reply, dict):
        payload = reply
    else:
        text = str(reply or "").strip()
        if text.startswith("```"):
            raise ValueError("AI planner must return raw structured JSON.")
        payload = json.loads(text)
    if "graph" in payload:
        payload = payload["graph"]
    return NativeTaskGraphSerializer.from_dict(payload)


def apply_registry_permissions(graph, snapshot):
    nodes = []
    for node in graph.nodes:
        descriptor = snapshot.get(node.capability_id)
        nodes.append(
            replace(
                node,
                permission_requirement=descriptor.permission_requirement,
            )
            if descriptor
            else node
        )
    return replace(graph, nodes=tuple(nodes))


def mappings_from_graph(graph):
    from jarvis.capability_planning.models import SuccessCriterionMapping
    from jarvis.native_task_graph import VerificationLevel

    result = []
    for item in graph.metadata.get("successCriteriaMappings", ()):
        result.append(
            SuccessCriterionMapping(
                criterion_id=str(item["criterionId"]),
                node_id=str(item["nodeId"]),
                output_key=str(item["outputKey"]),
                verification_level=VerificationLevel(item["verificationLevel"]),
            )
        )
    return tuple(result)


def ai_diagnostics(
    request, started, graph=None, *, validation_issues=(), failure="", repair_count=0
):
    input_length, input_hash = (
        PlannerDiagnosticsSanitizer.input_fingerprint(
            request.goal.original_input
        )
    )
    return PlannerDiagnostics(
        planner_type=PlannerType.AI.value,
        planner_duration_ms=int((perf_counter() - started) * 1000),
        selected_capabilities=tuple(
            node.capability_id
            for node in graph.nodes
            if node.capability_id
        )
        if graph
        else (),
        repair_count=repair_count,
        validation_issues=tuple(validation_issues),
        capability_snapshot_id=request.capability_snapshot.snapshot_id,
        registry_hash=request.capability_snapshot.registry_hash,
        routing_reason="ai_planner_fallback",
        confidence=0.85 if graph else 0.0,
        ai_failure=PlannerDiagnosticsSanitizer.sanitize_text(failure),
        input_length=input_length,
        input_hash=input_hash,
        entity_summary=PlannerDiagnosticsSanitizer.entity_summary(
            request.semantic_context
        ),
    )


def failed_result(request, message, started):
    return PlannerResult(
        status=PlannerStatus.FAILED,
        graph=None,
        planner_type=PlannerType.AI,
        model_id="",
        capability_snapshot_id=request.capability_snapshot.snapshot_id,
        confidence=0.0,
        diagnostics=ai_diagnostics(
            request, started, failure=sanitize_failure(message)
        ),
    )


def sanitize_failure(value):
    return PlannerDiagnosticsSanitizer.sanitize_text(value)


def provider_model(provider):
    try:
        return str(getattr(provider.metadata(), "model", "") or "")
    except Exception:
        return ""


def generate_with_timeout(provider, prompt, timeout_seconds):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-planner")
    future = executor.submit(provider.generate, prompt)
    try:
        return future.result(timeout=float(timeout_seconds))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
