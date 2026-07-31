"""Verification, retry, replan, and recovery contracts for reliable execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import random
from typing import Any
from uuid import uuid4

from jarvis.native_task_graph import (
    BindingSourceType,
    BackoffStrategy,
    FailureAction,
    PermissionRequirement,
    VerificationLevel,
)


def utc_now():
    return datetime.now(timezone.utc)


class VerificationStatus(str, Enum):
    PASSED = "Passed"
    FAILED = "Failed"
    INCONCLUSIVE = "Inconclusive"
    NEEDS_USER_CONFIRMATION = "NeedsUserConfirmation"
    SKIPPED = "Skipped"


class RecommendedAction(str, Enum):
    CONTINUE = "Continue"
    RETRY = "Retry"
    REQUEST_USER_INPUT = "RequestUserInput"
    REPLAN = "Replan"
    FAIL_GRAPH = "FailGraph"
    REQUIRE_CONFIRMATION = "RequireConfirmation"


class ErrorCategory(str, Enum):
    NONE = "None"
    TIMEOUT = "Timeout"
    RATE_LIMIT = "RateLimit"
    TEMPORARY_UNAVAILABLE = "TemporaryUnavailable"
    NETWORK = "Network"
    TRANSIENT_PROVIDER_FAILURE = "TransientProviderFailure"
    INVALID_INPUT = "InvalidInput"
    PERMISSION_DENIED = "PermissionDenied"
    AUTHENTICATION_FAILED = "AuthenticationFailed"
    RESTRICTED_OPERATION = "RestrictedOperation"
    NOT_FOUND = "NotFound"
    MULTIPLE_CANDIDATES = "MultipleCandidates"
    SCHEMA_VIOLATION = "SchemaViolation"
    SEMANTIC_MISMATCH = "SemanticMismatch"
    UNKNOWN = "Unknown"


class ExecutionOutcome(str, Enum):
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    PARTIAL = "Partial"
    PERMISSION_DENIED = "PermissionDenied"
    NEEDS_USER_INPUT = "NeedsUserInput"
    RETRY_EXHAUSTED = "RetryExhausted"
    REPLAN_EXHAUSTED = "ReplanExhausted"
    VERIFICATION_FAILED = "VerificationFailed"


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    verification_level: VerificationLevel
    confidence: float
    evidence: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE
    verified_at: datetime = field(default_factory=utc_now)
    verifier_type: str = "NodeResultVerifier"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_successful(self):
        return self.status in {
            VerificationStatus.PASSED,
            VerificationStatus.SKIPPED,
        }


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    attempt_number: int
    delay_seconds: float = 0.0
    reason: str = ""
    use_fallback_provider: bool = False
    exhausted: bool = False


@dataclass(frozen=True)
class AttemptRecord:
    attempt_number: int
    provider_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    execution_status: str
    error_category: ErrorCategory
    error_code: str
    retryable: bool
    verification_status: VerificationStatus
    idempotency_key: str
    output_hash: str

    def to_dict(self):
        return {
            "attemptNumber": self.attempt_number,
            "providerId": self.provider_id,
            "startedAt": self.started_at.isoformat(),
            "completedAt": self.completed_at.isoformat(),
            "durationSeconds": self.duration_seconds,
            "executionStatus": self.execution_status,
            "errorCategory": self.error_category.value,
            "errorCode": self.error_code,
            "retryable": self.retryable,
            "verificationStatus": self.verification_status.value,
            "idempotencyKey": self.idempotency_key,
            "outputHash": self.output_hash,
        }

    @classmethod
    def from_dict(cls, value):
        started_at = parse_time(value["startedAt"])
        completed_at = parse_time(value["completedAt"])
        return cls(
            attempt_number=int(value["attemptNumber"]),
            provider_id=str(value.get("providerId", "")),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=float(
                value.get(
                    "durationSeconds",
                    max(0.0, (completed_at - started_at).total_seconds()),
                )
            ),
            execution_status=str(value.get("executionStatus", "")),
            error_category=ErrorCategory(
                value.get("errorCategory", ErrorCategory.UNKNOWN.value)
            ),
            error_code=str(value.get("errorCode", "")),
            retryable=bool(value.get("retryable", False)),
            verification_status=VerificationStatus(
                value.get(
                    "verificationStatus",
                    VerificationStatus.SKIPPED.value,
                )
            ),
            idempotency_key=str(value.get("idempotencyKey", "")),
            output_hash=str(value.get("outputHash", "")),
        )


@dataclass(frozen=True)
class CriterionResult:
    success_criterion_id: str
    status: VerificationStatus
    node_id: str
    output_key: str
    verification_level: VerificationLevel
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoalVerificationResult:
    status: VerificationStatus
    criterion_results: tuple[CriterionResult, ...]
    overall_confidence: float
    missing_criteria: tuple[str, ...] = ()
    failed_criteria: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE


class CapabilityExecutionError(RuntimeError):
    def __init__(self, message, *, category=ErrorCategory.UNKNOWN, code=""):
        super().__init__(message)
        self.category = ErrorCategory(category)
        self.code = str(code)


class NodeResultVerifier:
    """Verify normalized outputs without retaining raw provider responses."""

    def __init__(self, *, semantic_verifier=None, read_back_verifier=None):
        self.semantic_verifier = semantic_verifier or SemanticVerifier()
        self.read_back_verifier = read_back_verifier or ExternalReadBackVerifier()

    def verify(self, node, inputs, outputs, *, adapter=None):
        policy = node.verification_policy
        level = policy.verification_level
        problems = []
        for key, definition in node.outputs.items():
            if definition.is_required and key not in outputs:
                problems.append(f"required_output_missing:{key}")
            elif key in outputs and not value_matches_type(
                outputs[key], definition.value_type
            ):
                problems.append(f"output_type_mismatch:{key}")
        if problems:
            return VerificationResult(
                VerificationStatus.FAILED,
                VerificationLevel.SCHEMA,
                0.0,
                problems=tuple(problems),
                recommended_action=RecommendedAction.FAIL_GRAPH,
                diagnostics={"verificationCode": "schema_violation"},
            )
        if level == VerificationLevel.NONE:
            return VerificationResult(
                VerificationStatus.SKIPPED,
                level,
                1.0,
                evidence=("schema_valid_verification_not_required",),
            )
        if level == VerificationLevel.SCHEMA:
            return VerificationResult(
                VerificationStatus.PASSED,
                level,
                1.0,
                evidence=("output_schema_valid",),
            )
        semantic = self.semantic_verifier.verify(node, inputs, outputs)
        if not semantic.is_successful:
            return semantic
        if level == VerificationLevel.EXTERNAL_READ_BACK:
            return self.read_back_verifier.verify(
                node, inputs, outputs, adapter=adapter
            )
        if level == VerificationLevel.USER_CONFIRMATION:
            return VerificationResult(
                VerificationStatus.NEEDS_USER_CONFIRMATION,
                level,
                semantic.confidence,
                evidence=semantic.evidence,
                recommended_action=RecommendedAction.REQUIRE_CONFIRMATION,
            )
        return semantic


class SemanticVerifier:
    COMPARABLE_FIELDS = {
        "start_time",
        "startTime",
        "time",
        "date",
        "event_id",
        "eventId",
        "recipient",
        "status",
    }

    def verify(self, node, inputs, outputs):
        comparable = []
        flattened = flatten_values(outputs)
        search_values = [
            value
            for key, value in outputs.items()
            if key in {"contacts", "events", "candidates", "results"}
            and isinstance(value, (list, tuple))
        ]
        if search_values and len(search_values[0]) == 0:
            return VerificationResult(
                VerificationStatus.FAILED,
                VerificationLevel.SEMANTIC,
                0.0,
                problems=("not_found",),
                recommended_action=RecommendedAction.REPLAN,
                verifier_type="SemanticVerifier",
                diagnostics={"verificationCode": "not_found"},
            )
        if search_values and len(search_values[0]) > 1 and node.metadata.get(
            "requiresSingleResult", False
        ):
            return VerificationResult(
                VerificationStatus.INCONCLUSIVE,
                VerificationLevel.SEMANTIC,
                0.5,
                problems=("multiple_candidates",),
                recommended_action=RecommendedAction.REQUEST_USER_INPUT,
                verifier_type="SemanticVerifier",
                diagnostics={"verificationCode": "multiple_candidates"},
            )
        if node.capability_id == "mail.send":
            status = str(flattened.get("status", "")).lower()
            message_id = flattened.get("messageId", flattened.get("message_id"))
            if not message_id or status not in {"sent", "delivered", "queued"}:
                return VerificationResult(
                    VerificationStatus.FAILED,
                    VerificationLevel.SEMANTIC,
                    0.0,
                    problems=("mail_sent_state_unconfirmed",),
                    recommended_action=RecommendedAction.RETRY,
                    verifier_type="SemanticVerifier",
                    diagnostics={"verificationCode": "mail_not_sent"},
                )
        for key, expected in inputs.items():
            if key not in self.COMPARABLE_FIELDS or expected in (None, ""):
                continue
            aliases = {
                "time": ("time", "start_time", "startTime"),
                "start_time": ("start_time", "startTime", "time"),
                "startTime": ("startTime", "start_time", "time"),
                "event_id": ("event_id", "eventId", "id"),
                "eventId": ("eventId", "event_id", "id"),
            }.get(key, (key,))
            actual_key = next(
                (item for item in aliases if item in flattened), None
            )
            if actual_key:
                comparable.append((key, expected, flattened[actual_key]))
        mismatches = [
            key
            for key, expected, actual in comparable
            if canonical_value(expected) != canonical_value(actual)
        ]
        if mismatches:
            return VerificationResult(
                VerificationStatus.FAILED,
                VerificationLevel.SEMANTIC,
                0.0,
                problems=tuple(f"semantic_mismatch:{key}" for key in mismatches),
                recommended_action=RecommendedAction.REPLAN,
                verifier_type="SemanticVerifier",
                diagnostics={"verificationCode": "semantic_mismatch"},
            )
        return VerificationResult(
            VerificationStatus.PASSED,
            VerificationLevel.SEMANTIC,
            1.0 if comparable else 0.9,
            evidence=("semantic_constraints_satisfied",),
            verifier_type="SemanticVerifier",
        )


class ExternalReadBackVerifier:
    def verify(self, node, inputs, outputs, *, adapter=None):
        capability_id = node.verification_policy.read_back_capability_id
        if adapter is None or not capability_id:
            return VerificationResult(
                VerificationStatus.INCONCLUSIVE,
                VerificationLevel.EXTERNAL_READ_BACK,
                0.0,
                problems=("read_back_unavailable",),
                recommended_action=RecommendedAction.REQUEST_USER_INPUT,
                verifier_type="ExternalReadBackVerifier",
            )
        try:
            actual = adapter.read_back(
                node, inputs, outputs, capability_id=capability_id
            )
        except Exception as error:
            return VerificationResult(
                VerificationStatus.INCONCLUSIVE,
                VerificationLevel.EXTERNAL_READ_BACK,
                0.0,
                problems=(f"read_back_failed:{classify_error(error).value}",),
                recommended_action=RecommendedAction.RETRY,
                verifier_type="ExternalReadBackVerifier",
            )
        semantic = SemanticVerifier().verify(node, inputs, normalize_mapping(actual))
        if not semantic.is_successful:
            return VerificationResult(
                semantic.status,
                VerificationLevel.EXTERNAL_READ_BACK,
                semantic.confidence,
                semantic.evidence,
                semantic.problems,
                semantic.recommended_action,
                verifier_type="ExternalReadBackVerifier",
                diagnostics=semantic.diagnostics,
            )
        return VerificationResult(
            VerificationStatus.PASSED,
            VerificationLevel.EXTERNAL_READ_BACK,
            1.0,
            evidence=("external_read_back_matched",),
            verifier_type="ExternalReadBackVerifier",
        )


class GoalVerifier:
    def verify(self, goal, mappings, session, node_verifications):
        if goal is None:
            return GoalVerificationResult(
                VerificationStatus.SKIPPED, (), 1.0, evidence=("goal_not_supplied",)
            )
        mapping_by_criterion = {item.criterion_id: item for item in mappings}
        results = []
        missing = []
        failed = []
        optional_failed = []
        criteria_by_id = {
            item.criterion_id: item for item in goal.success_criteria
        }
        for criterion_id, criterion in criteria_by_id.items():
            mapping = mapping_by_criterion.get(criterion_id)
            if mapping is None:
                if criterion.required:
                    missing.append(criterion_id)
                continue
            verification = node_verifications.get(mapping.node_id)
            output_exists = session.output_store.has(
                mapping.node_id, mapping.output_key
            )
            status = (
                VerificationStatus.FAILED
                if not output_exists
                else (
                    verification.status
                    if verification is not None
                    else VerificationStatus.PASSED
                )
            )
            confidence = (
                0.0
                if not output_exists
                else (
                    verification.confidence
                    if verification
                    else 1.0
                )
            )
            if status not in {
                VerificationStatus.PASSED,
                VerificationStatus.SKIPPED,
            }:
                failed.append(criterion_id)
                if not criterion.required:
                    optional_failed.append(criterion_id)
            results.append(
                CriterionResult(
                    criterion_id,
                    status,
                    mapping.node_id,
                    mapping.output_key,
                    mapping.verification_level,
                    confidence,
                    verification.evidence if verification else (),
                )
            )
        required_failed = [
            item
            for item in failed
            if criteria_by_id[item].required
        ]
        passed = not missing and not required_failed and not optional_failed
        confidence = (
            min((item.confidence for item in results), default=1.0)
            if passed
            else 0.0
        )
        return GoalVerificationResult(
            (
                VerificationStatus.PASSED
                if passed
                else (
                    VerificationStatus.INCONCLUSIVE
                    if not missing and not required_failed
                    else VerificationStatus.FAILED
                )
            ),
            tuple(results),
            confidence,
            tuple(missing),
            tuple(failed),
            tuple(
                evidence
                for item in results
                for evidence in item.evidence
            ),
            (
                RecommendedAction.CONTINUE
                if passed
                else RecommendedAction.REPLAN
            ),
        )


class RetryController:
    DEFAULT_RETRYABLE = {
        ErrorCategory.TIMEOUT,
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TEMPORARY_UNAVAILABLE,
        ErrorCategory.NETWORK,
        ErrorCategory.TRANSIENT_PROVIDER_FAILURE,
    }

    def __init__(self, *, random_source=None):
        self.random_source = random_source or random.Random()

    def decide(
        self,
        *,
        policy,
        attempt_number,
        error_category=ErrorCategory.NONE,
        error_code="",
        verification_result=None,
        external_mutation=False,
    ):
        category = ErrorCategory(error_category)
        verification_retry = (
            verification_result is not None
            and verification_result.recommended_action == RecommendedAction.RETRY
        )
        allowed_category = (
            category in self.DEFAULT_RETRYABLE
            or category.value in policy.retryable_categories
        )
        allowed_code = bool(
            error_code and error_code in policy.retryable_error_codes
        )
        retryable = verification_retry or allowed_category or allowed_code
        exhausted = retryable and attempt_number >= policy.max_attempts
        if not retryable or exhausted:
            return RetryDecision(
                False,
                attempt_number,
                reason=(category.value if category != ErrorCategory.NONE else "verification"),
                exhausted=exhausted,
            )
        delay = calculate_delay(policy, attempt_number, self.random_source)
        fallback = (
            policy.provider_fallback_allowed
            and not external_mutation
            and attempt_number >= 1
        )
        return RetryDecision(
            True,
            attempt_number + 1,
            delay,
            category.value if category != ErrorCategory.NONE else "verification",
            fallback,
            False,
        )


@dataclass(frozen=True)
class ReplanTrigger:
    reason: str
    failed_node_id: str
    failure_category: ErrorCategory
    evidence: tuple[str, ...] = ()
    completed_node_ids: tuple[str, ...] = ()
    reusable_outputs: tuple[dict, ...] = ()
    user_input_required: bool = False
    suggested_constraints: tuple[str, ...] = ()

    @classmethod
    def from_failure(
        cls,
        *,
        node_id,
        category,
        session,
        evidence=(),
        user_input_required=False,
    ):
        completed = tuple(
            key
            for key, record in session.node_records.items()
            if getattr(record.state, "value", "") == "Succeeded"
        )
        reusable = tuple(
            {
                "nodeId": item.node_id,
                "outputKey": item.output_key,
                "valueType": item.value_type,
                "outputHash": safe_hash(item.value),
            }
            for item in session.output_store.values()
        )
        category = ErrorCategory(category)
        return cls(
            reason={
                ErrorCategory.NOT_FOUND: "target_not_found",
                ErrorCategory.MULTIPLE_CANDIDATES: "multiple_candidates",
                ErrorCategory.SEMANTIC_MISMATCH: "invalid_plan_assumption",
            }.get(category, "execution_assumption_failed"),
            failed_node_id=node_id,
            failure_category=category,
            evidence=tuple(evidence),
            completed_node_ids=completed,
            reusable_outputs=reusable,
            user_input_required=user_input_required,
        )


@dataclass(frozen=True)
class ReplanRequest:
    goal_specification: Any
    current_graph: Any
    current_snapshot: Any
    failed_node_id: str
    trigger: ReplanTrigger
    completed_nodes: tuple[str, ...]
    reusable_outputs: tuple[dict, ...]
    artifact_refs: tuple[dict, ...]
    capability_registry_snapshot: Any
    current_conversation_context: Any
    current_session: Any = None
    user_supplied_clarification: Any = None
    max_replan_nodes: int = 8
    correlation_id: str = ""


@dataclass(frozen=True)
class ReplanDecision:
    allowed: bool
    request: ReplanRequest | None = None
    reason: str = ""
    exhausted: bool = False


@dataclass(frozen=True)
class ReplanResult:
    succeeded: bool
    graph: Any = None
    planner_result: Any = None
    snapshot: Any = None
    validation_report: Any = None
    session: Any = None
    binding_context: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def selected_candidate_output(session, trigger, clarification):
    """Resolve an ordinal follow-up against transient candidate output."""
    if (
        trigger.failure_category != ErrorCategory.MULTIPLE_CANDIDATES
        or not clarification
    ):
        return None
    record = session.node_records.get(trigger.failed_node_id)
    if record is None:
        return None
    candidate_key = next(
        (
            key
            for key in ("contacts", "events", "candidates", "results")
            if isinstance(record.pending_outputs.get(key), (list, tuple))
        ),
        "",
    )
    if not candidate_key:
        return None
    candidates = record.pending_outputs[candidate_key]
    ordinal = clarification_ordinal(clarification)
    if ordinal is None or ordinal < 1 or ordinal > len(candidates):
        return None
    selected = candidates[ordinal - 1]
    value = [selected] if candidate_key in {"contacts", "events"} else selected
    return {
        "nodeId": trigger.failed_node_id,
        "outputKey": candidate_key,
        "valueType": "ContactList"
        if candidate_key == "contacts"
        else "CalendarEventList"
        if candidate_key == "events"
        else "Any",
        "outputHash": safe_hash(value),
        "value": value,
    }


def clarification_ordinal(value):
    """Return a one-based candidate ordinal from a short voice answer."""
    import re

    text = str(value or "").strip().lower()
    match = re.search(r"(?<!\d)(\d+)(?:\s*번|\s*번째)?", text)
    if match:
        return int(match.group(1))
    aliases = {
        "첫": 1,
        "첫번째": 1,
        "첫 번째": 1,
        "하나": 1,
        "두번째": 2,
        "두 번째": 2,
        "둘": 2,
        "세번째": 3,
        "세 번째": 3,
        "셋": 3,
        "first": 1,
        "second": 2,
        "third": 3,
    }
    return next(
        (ordinal for phrase, ordinal in aliases.items() if phrase in text),
        None,
    )


class ReplanController:
    def __init__(
        self,
        planner=None,
        *,
        validator=None,
        snapshot_factory=None,
        event_bus=None,
        max_attempts=2,
    ):
        self.planner = planner
        self.validator = validator
        self.snapshot_factory = snapshot_factory
        self.event_bus = event_bus
        self.max_attempts = max_attempts

    def build_request(
        self,
        *,
        goal,
        graph,
        snapshot,
        session,
        trigger,
        capability_snapshot,
        conversation_context=None,
        correlation_id="",
        attempt_number=0,
        previous_failure_reasons=(),
        user_supplied_clarification=None,
    ):
        if attempt_number >= self.max_attempts:
            return ReplanDecision(False, reason="max_replan_attempts", exhausted=True)
        if (
            previous_failure_reasons
            and previous_failure_reasons[-1] == trigger.reason
        ):
            return ReplanDecision(False, reason="repeated_failure", exhausted=True)
        completed = tuple(
            node_id
            for node_id, record in session.node_records.items()
            if str(record.state.value) == "Succeeded"
        )
        reusable = tuple(
            {
                "nodeId": value.node_id,
                "outputKey": value.output_key,
                "valueType": value.value_type,
                "outputHash": safe_hash(value.value),
                "value": value.value,
            }
            for value in session.output_store.values()
        )
        selection = selected_candidate_output(
            session,
            trigger,
            user_supplied_clarification,
        )
        if (
            trigger.failure_category == ErrorCategory.MULTIPLE_CANDIDATES
            and user_supplied_clarification
            and selection is None
        ):
            return ReplanDecision(False, reason="invalid_candidate_selection")
        if selection is not None:
            completed = (*completed, trigger.failed_node_id)
            reusable = (*reusable, selection)
        request = ReplanRequest(
            goal,
            graph,
            snapshot,
            trigger.failed_node_id,
            trigger,
            completed,
            reusable,
            (),
            capability_snapshot,
            conversation_context,
            current_session=session,
            user_supplied_clarification=user_supplied_clarification,
            max_replan_nodes=8,
            correlation_id=correlation_id,
        )
        return ReplanDecision(True, request=request)

    def replan(self, decision, *, mappings=()):
        if not decision.allowed or decision.request is None:
            return ReplanResult(
                False, reason=decision.reason or "replan_not_allowed"
            )
        if self.planner is None or self.validator is None or self.snapshot_factory is None:
            return ReplanResult(False, reason="replan_runtime_not_configured")
        request = decision.request
        self._emit(
            "runtime.execution.replan_started",
            request,
            node_id=request.failed_node_id,
        )
        if hasattr(self.planner, "replan"):
            planner_result = self.planner.replan(request)
        else:
            planner_result = self.planner(request)
        if getattr(getattr(planner_result, "status", None), "value", "") != "Planned":
            self._emit(
                "runtime.execution.replan_failed",
                request,
                node_id=request.failed_node_id,
                reason="planner_failed",
            )
            return ReplanResult(False, planner_result=planner_result, reason="planner_failed")
        if not mappings:
            mappings = tuple(
                getattr(planner_result, "success_criteria_mappings", ())
            )
        graph = planner_result.graph
        completed_ids = set(request.completed_nodes)
        if completed_ids:
            remaining_nodes = []
            for node in graph.nodes:
                if node.node_id in completed_ids:
                    continue
                rebound = {}
                for name, binding in node.inputs.items():
                    if (
                        binding.source_type == BindingSourceType.NODE_OUTPUT
                        and binding.source_node_id in completed_ids
                    ):
                        rebound[name] = replace(
                            binding,
                            source_type=BindingSourceType.PREVIOUS_RESULT,
                            source_node_id="",
                            source_key=(
                                f"{binding.source_node_id}.{binding.source_key}"
                            ),
                        )
                    else:
                        rebound[name] = binding
                remaining_nodes.append(replace(node, inputs=rebound))
            graph = replace(
                graph,
                nodes=tuple(remaining_nodes),
                edges=tuple(
                    edge
                    for edge in graph.edges
                    if edge.source_node_id not in completed_ids
                    and edge.target_node_id not in completed_ids
                ),
                outputs=tuple(
                    output
                    for output in graph.outputs
                    if output.source_node_id not in completed_ids
                ),
            )
        metadata = dict(graph.metadata)
        metadata.update(
            {
                "parentGraphId": request.current_graph.graph_id,
                "previousGraphVersion": request.current_graph.version,
                "completedNodeIds": list(request.completed_nodes),
            }
        )
        if graph.graph_id == request.current_graph.graph_id:
            graph = replace(graph, graph_id=f"graph-{uuid4()}", metadata=metadata)
        else:
            graph = replace(graph, metadata=metadata)
        planner_result = replace(planner_result, graph=graph)
        report = self.validator.validate(
            graph,
            request.capability_registry_snapshot,
            goal=request.goal_specification,
            mappings=mappings,
            max_nodes=request.max_replan_nodes,
        )
        if not report.is_valid:
            self._emit(
                "runtime.execution.replan_failed",
                request,
                node_id=request.failed_node_id,
                reason="validation_failed",
            )
            return ReplanResult(
                False,
                graph=graph,
                planner_result=planner_result,
                validation_report=report,
                reason="validation_failed",
            )
        snapshot = self.snapshot_factory.create(
            planner_result,
            request.capability_registry_snapshot,
            goal=request.goal_specification,
            mappings=mappings,
            max_nodes=request.max_replan_nodes,
        )
        from .models import GraphExecutionSession

        old_session = request.current_session
        session = GraphExecutionSession.create(graph, snapshot)
        if old_session is not None:
            session.goal_execution_id = old_session.goal_execution_id
            session.previous_session_ids = (
                *old_session.previous_session_ids,
                old_session.session_id,
            )
            session.replan_count = old_session.replan_count + 1
            from .models import TypedOutput

            for value in old_session.output_store.values():
                session.output_store.put(
                    TypedOutput(
                        value.node_id,
                        value.output_key,
                        value.value_type,
                        value.value,
                        value.created_at,
                    )
                )
        previous_results = {}
        for item in request.reusable_outputs:
            previous_results[
                f"{item['nodeId']}.{item['outputKey']}"
            ] = item.get("value")
            previous_results.setdefault(
                item["outputKey"], item.get("value")
            )
        result = ReplanResult(
            True,
            graph,
            planner_result,
            snapshot,
            report,
            session,
            {"previous_results": previous_results},
        )
        self._emit(
            "runtime.execution.replan_completed",
            request,
            node_id=request.failed_node_id,
            new_graph_id=graph.graph_id,
            new_snapshot_id=snapshot.snapshot_id,
        )
        return result

    def _emit(self, event_type, request, **payload):
        if self.event_bus is None:
            return
        from jarvis.core.events.event import BaseEvent

        session = request.current_session
        self.event_bus.publish(
            BaseEvent(
                event_type=event_type,
                aggregate_type="GraphExecutionSession",
                aggregate_id=(
                    session.session_id
                    if session is not None
                    else request.current_graph.graph_id
                ),
                correlation_id=request.correlation_id,
                payload={
                    "goal_execution_id": (
                        session.goal_execution_id
                        if session is not None
                        else ""
                    ),
                    "session_id": (
                        session.session_id if session is not None else ""
                    ),
                    "snapshot_id": request.current_snapshot.snapshot_id,
                    "graph_id": request.current_graph.graph_id,
                    "retry_count": (
                        session.retry_count if session is not None else 0
                    ),
                    "replan_count": (
                        session.replan_count if session is not None else 0
                    ),
                    "attempt_number": 0,
                    **payload,
                },
            )
        )


class RecoveryController:
    """Classify interrupted checkpoint states without replaying mutations."""

    def recover(self, session, graph):
        actions = {}
        for node in graph.nodes:
            record = session.node_records[node.node_id]
            if str(record.state.value) not in {
                "Running",
                "WaitingForProvider",
                "VerificationPending",
                "RetryPending",
                "Retrying",
            }:
                continue
            mutation = node.permission_requirement != PermissionRequirement.SAFE
            actions[node.node_id] = (
                "ReadBack" if mutation else "Retry"
            )
        return actions


def calculate_delay(policy, attempt_number, random_source):
    base = policy.delay_seconds
    if policy.backoff_strategy == BackoffStrategy.LINEAR:
        delay = base * attempt_number
    elif policy.backoff_strategy == BackoffStrategy.EXPONENTIAL:
        delay = base * (2 ** max(0, attempt_number - 1))
    else:
        delay = base
    delay = min(delay, policy.max_delay_seconds)
    if policy.jitter and delay:
        delay = random_source.uniform(delay * 0.5, delay)
    return delay


def classify_error(error):
    if isinstance(error, CapabilityExecutionError):
        return error.category
    name = type(error).__name__.lower()
    message = str(error).lower()
    if isinstance(error, TimeoutError) or "timeout" in name or "timeout" in message:
        return ErrorCategory.TIMEOUT
    if "429" in message or "rate limit" in message:
        return ErrorCategory.RATE_LIMIT
    if "permission" in message or "forbidden" in message:
        return ErrorCategory.PERMISSION_DENIED
    if "auth" in message or "credential" in message:
        return ErrorCategory.AUTHENTICATION_FAILED
    if "not found" in message:
        return ErrorCategory.NOT_FOUND
    if "network" in message or "connection" in message:
        return ErrorCategory.NETWORK
    if isinstance(error, (TypeError, ValueError)):
        return ErrorCategory.INVALID_INPUT
    return ErrorCategory.UNKNOWN


def value_matches_type(value, value_type):
    if value_type in {"Any", "object", ""}:
        return True
    basic = {
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
        "float": (int, float),
        "array": (list, tuple),
    }
    expected = basic.get(value_type.lower())
    if expected is not None:
        return isinstance(value, expected) and not (
            value_type.lower() in {"integer", "number", "float"}
            and isinstance(value, bool)
        )
    return value is not None


def flatten_values(value):
    if not isinstance(value, dict):
        if hasattr(value, "__dict__"):
            value = vars(value)
        else:
            return {}
    flattened = dict(value)
    for item in value.values():
        if isinstance(item, dict):
            flattened.update(item)
        elif hasattr(item, "__dict__"):
            flattened.update(vars(item))
    return flattened


def normalize_mapping(value):
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {"result": value}


def canonical_value(value):
    if isinstance(value, str):
        return value.strip().lower()
    return value


def safe_hash(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        default=lambda item: vars(item) if hasattr(item, "__dict__") else str(item),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def idempotency_key(goal_id, graph_version, node_id):
    logical = f"{goal_id}:{graph_version}:{node_id}"
    return hashlib.sha256(logical.encode("utf-8")).hexdigest()
