"""Sequential fail-closed executor for validated NativeTaskGraph plans."""

from __future__ import annotations

import operator
import re
import time
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone

from jarvis.abilities.result import AbilityResult
from jarvis.capability_planning import SnapshotVerifier
from jarvis.core.events.event import BaseEvent
from jarvis.native_task_graph import (
    EdgeType,
    NodeType,
    PermissionRequirement,
    VerificationLevel,
    VerificationPolicy,
)

from .models import (
    GraphExecutionResult,
    GraphExecutionSession,
    GraphExecutionState,
    ExecutionWaitingReason,
    ExecutionSummary,
    NodeExecutionState,
    TypedOutput,
)
from .resolver import InputBindingResolver
from .reliability import (
    AttemptRecord,
    ErrorCategory,
    ExecutionOutcome,
    GoalVerifier,
    NodeResultVerifier,
    RecommendedAction,
    RecoveryController,
    ReplanTrigger,
    RetryController,
    VerificationStatus,
    classify_error,
    idempotency_key,
    safe_hash,
)


class ReliableExecutionFailure(RuntimeError):
    def __init__(
        self,
        message,
        outcome,
        *,
        error_category=ErrorCategory.UNKNOWN,
        recommended_action=None,
    ):
        super().__init__(message)
        self.outcome = outcome
        self.error_category = ErrorCategory(error_category)
        self.recommended_action = recommended_action


class InMemoryCheckpointStore:
    def __init__(self):
        self.checkpoints = {}

    def save(self, session):
        session.checkpoint_revision += 1
        checkpoint = session.to_checkpoint()
        self.checkpoints[session.session_id] = checkpoint
        return checkpoint


class CapabilityExecutionAdapter:
    """Provider-neutral CapabilityId adapter over existing AbilityRegistry."""

    OPERATION_MAP = {
        "get_forecast": "query",
        "search_events": "list",
        "create_event": "create",
        "update_event": "update",
        "delete_event": "delete",
        "search": "get",
    }

    def __init__(self, ability_registry=None, handlers=None):
        self.ability_registry = ability_registry
        self.handlers = dict(handlers or {})

    def execute(self, node, inputs):
        handler = self.handlers.get(node.capability_id)
        if handler is not None:
            return handler(dict(inputs))
        ability_id = node.capability_id.split(".", 1)[0]
        ability = self.ability_registry.get(ability_id) if self.ability_registry else None
        if ability is None:
            raise ValueError(f"No runtime Ability for capability: {node.capability_id}")
        if node.capability_id == "weather.get_forecast":
            from jarvis.abilities.native.weather.query import (
                WEATHER_CAPABILITY_FORECAST,
                WEATHER_DATE_TODAY,
                WEATHER_MODE_CURRENT,
                WEATHER_MODE_FORECAST,
                WeatherQuery,
            )

            date_value = str(inputs.get("date", WEATHER_DATE_TODAY))
            query = WeatherQuery(
                location=str(inputs.get("location", "")),
                date=date_value,
                mode=(
                    WEATHER_MODE_CURRENT
                    if date_value == WEATHER_DATE_TODAY
                    else WEATHER_MODE_FORECAST
                ),
                capability=(
                    "current_weather"
                    if date_value == WEATHER_DATE_TODAY
                    else WEATHER_CAPABILITY_FORECAST
                ),
                location_source="task_graph",
                date_source="task_graph",
            )
            result = ability.execute(query)
            if isinstance(result, AbilityResult):
                if not result.success:
                    raise RuntimeError(
                        result.error or f"{node.capability_id} failed"
                    )
                return result.data
            return result
        payload = dict(inputs)
        if node.capability_id == "contacts.search":
            payload.setdefault("display_name", payload.get("query", ""))
        if node.capability_id == "reminder.create":
            payload.setdefault("title", payload.get("message", ""))
        payload.setdefault(
            "action",
            self.OPERATION_MAP.get(node.operation, node.operation),
        )
        payload.setdefault("raw_text", "")
        result = ability.execute(payload)
        if isinstance(result, AbilityResult):
            if not result.success:
                raise RuntimeError(result.error or f"{node.capability_id} failed")
            return result.data
        return result

    def read_back(self, node, inputs, outputs, *, capability_id):
        handler = self.handlers.get(capability_id)
        payload = {
            "requested": dict(inputs),
            "result": dict(outputs),
            "sourceCapabilityId": node.capability_id,
        }
        if handler is not None:
            return handler(payload)
        domain, operation = capability_id.split(".", 1)
        ability = (
            self.ability_registry.get(domain)
            if self.ability_registry
            else None
        )
        if ability is None:
            raise ValueError(
                f"No read-back runtime Ability for capability: {capability_id}"
            )
        request = dict(inputs)
        request["action"] = self.OPERATION_MAP.get(operation, operation)
        request.setdefault("raw_text", "")
        if outputs:
            request["result"] = dict(outputs)
        result = ability.execute(request)
        if isinstance(result, AbilityResult):
            if not result.success:
                raise RuntimeError(
                    result.error or f"{capability_id} read-back failed"
                )
            return result.data
        return result


class GraphExecutor:
    def __init__(
        self,
        capability_adapter,
        *,
        snapshot_verifier=None,
        binding_resolver=None,
        permission_gate=None,
        checkpoint_store=None,
        event_bus=None,
        node_result_verifier=None,
        goal_verifier=None,
        retry_controller=None,
        verification_enabled=True,
        retry_enabled=False,
        replan_enabled=False,
        sleeper=None,
        recovery_controller=None,
    ):
        self.capability_adapter = capability_adapter
        self.snapshot_verifier = snapshot_verifier or SnapshotVerifier()
        self.binding_resolver = binding_resolver or InputBindingResolver()
        self.permission_gate = permission_gate or (lambda node, inputs: False)
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.event_bus = event_bus
        self.node_result_verifier = node_result_verifier or NodeResultVerifier()
        self.goal_verifier = goal_verifier or GoalVerifier()
        self.retry_controller = retry_controller or RetryController()
        self.verification_enabled = bool(verification_enabled)
        self.retry_enabled = bool(retry_enabled)
        self.replan_enabled = bool(replan_enabled)
        self.sleeper = sleeper or time.sleep
        self.recovery_controller = recovery_controller or RecoveryController()

    def execute(
        self,
        graph,
        snapshot,
        validation_report,
        *,
        confirmed_node_ids=(),
        correlation_id="",
        binding_context=None,
        session=None,
        goal=None,
        success_criteria_mappings=(),
    ):
        verified = self.snapshot_verifier.verify(
            snapshot, graph, validation_report
        )
        if not verified.is_valid:
            self.emit(
                "runtime.execution.snapshot_verification_failed",
                snapshot.snapshot_id,
                correlation_id,
                graph_id=graph.graph_id,
                snapshot_id=snapshot.snapshot_id,
                issue_codes=[issue.code for issue in verified.issues],
            )
            raise ValueError(
                "Snapshot verification failed: "
                + ", ".join(issue.code for issue in verified.issues)
            )
        if session is None:
            self.emit(
                "runtime.execution.snapshot_verified",
                snapshot.snapshot_id,
                correlation_id,
                graph_id=graph.graph_id,
                snapshot_id=snapshot.snapshot_id,
                graph_hash=snapshot.graph_hash,
            validation_hash=snapshot.validation_hash,
            planning_confidence=snapshot.planning_confidence,
            planner_type=snapshot.planner_metadata["plannerType"],
            capability_snapshot_id=snapshot.planner_metadata[
                "capabilitySnapshotId"
            ],
            graph_version=graph.version,
            schema_version=graph.schema_version,
            verified_at=datetime.now(timezone.utc).isoformat(),
            )
            session = GraphExecutionSession.create(graph, snapshot)
            session.started_at = datetime.now(timezone.utc)
            session.state = GraphExecutionState.RUNNING
            self.emit_session("runtime.execution.session_created", session, correlation_id)
            self.checkpoint_store.save(session)
        else:
            if (
                session.snapshot_id != snapshot.snapshot_id
                or session.graph_id != graph.graph_id
                or session.graph_version != graph.version
            ):
                raise ValueError("Execution session does not match the plan snapshot.")
            if (
                session.state == GraphExecutionState.CREATED
                and session.started_at is None
            ):
                self.emit(
                    "runtime.execution.snapshot_verified",
                    snapshot.snapshot_id,
                    correlation_id,
                    graph_id=graph.graph_id,
                    snapshot_id=snapshot.snapshot_id,
                    graph_hash=snapshot.graph_hash,
                    validation_hash=snapshot.validation_hash,
                    planning_confidence=snapshot.planning_confidence,
                    planner_type=snapshot.planner_metadata["plannerType"],
                    capability_snapshot_id=snapshot.planner_metadata[
                        "capabilitySnapshotId"
                    ],
                    graph_version=graph.version,
                    schema_version=graph.schema_version,
                    verified_at=datetime.now(timezone.utc).isoformat(),
                )
                session.started_at = datetime.now(timezone.utc)
                session.state = GraphExecutionState.RUNNING
                self.emit_session(
                    "runtime.execution.session_created",
                    session,
                    correlation_id,
                )
                self.checkpoint_store.save(session)
            interrupted = any(
                record.state
                in {
                    NodeExecutionState.RUNNING,
                    NodeExecutionState.WAITING_FOR_PROVIDER,
                    NodeExecutionState.VERIFICATION_PENDING,
                    NodeExecutionState.RETRY_PENDING,
                    NodeExecutionState.RETRYING,
                }
                for record in session.node_records.values()
            )
            if interrupted:
                self.emit_session(
                    "runtime.execution.recovery_started",
                    session,
                    correlation_id,
                )
                actions = self.recovery_controller.recover(session, graph)
                for node_id, action in actions.items():
                    node = graph.node(node_id)
                    record = session.node_records[node_id]
                    if action == "Retry":
                        record.state = NodeExecutionState.PENDING
                        session.recovery_path = (
                            *session.recovery_path,
                            f"{node_id}:Retry",
                        )
                        continue
                    capability_id = (
                        node.verification_policy.read_back_capability_id
                    )
                    if not capability_id:
                        return self.fail(
                            graph,
                            session,
                            node,
                            "Interrupted mutation requires read-back.",
                            correlation_id,
                            outcome=ExecutionOutcome.NEEDS_USER_INPUT,
                        )
                    try:
                        session.provider_calls += 1
                        raw = self.capability_adapter.read_back(
                            node,
                            record.resolved_inputs,
                            {},
                            capability_id=capability_id,
                        )
                        recovered_outputs = normalize_outputs(node, raw)
                        verification = self.node_result_verifier.verify(
                            replace(
                                node,
                                verification_policy=VerificationPolicy(
                                    VerificationLevel.SEMANTIC
                                ),
                            ),
                            record.resolved_inputs,
                            recovered_outputs,
                        )
                    except Exception:
                        verification = None
                    if verification is None or not verification.is_successful:
                        return self.fail(
                            graph,
                            session,
                            node,
                            "Interrupted mutation state is inconclusive.",
                            correlation_id,
                            outcome=ExecutionOutcome.NEEDS_USER_INPUT,
                        )
                    for key, definition in node.outputs.items():
                        if key in recovered_outputs:
                            session.output_store.put(
                                TypedOutput(
                                    node.node_id,
                                    key,
                                    definition.value_type,
                                    recovered_outputs[key],
                                )
                            )
                    record.verification_result = verification
                    record.state = NodeExecutionState.SUCCEEDED
                    session.recovery_path = (
                        *session.recovery_path,
                        f"{node_id}:ReadBack",
                    )
                self.emit_session(
                    "runtime.execution.recovery_completed",
                    session,
                    correlation_id,
                    recovery_actions=actions,
                )
            for record in session.node_records.values():
                if record.state == NodeExecutionState.WAITING_FOR_PERMISSION:
                    record.state = NodeExecutionState.PENDING
            if session.permission_wait_started_at is not None:
                session.permission_wait_seconds += max(
                    0.0,
                    (
                        datetime.now(timezone.utc)
                        - session.permission_wait_started_at
                    ).total_seconds(),
                )
                session.permission_wait_started_at = None
            if session.state != GraphExecutionState.RUNNING:
                session.clear_waiting_reason()
                session.state = GraphExecutionState.RUNNING
                session.append_timeline("session_resumed")
        confirmed = set(confirmed_node_ids)
        context = dict(binding_context or {})

        while True:
            pending = [
                node for node in graph.nodes
                if session.node_records[node.node_id].state
                == NodeExecutionState.PENDING
            ]
            if not pending:
                break
            progressed = False
            for node in pending:
                decision = self.node_decision(graph, session, node)
                if decision == "wait":
                    continue
                if decision == "skip":
                    self.skip_node(session, node, correlation_id)
                    progressed = True
                    continue
                record = session.node_records[node.node_id]
                record.state = NodeExecutionState.READY
                session.append_timeline("node_ready", node.node_id)
                self.emit_node("runtime.execution.node_ready", session, node, correlation_id)
                inputs = self.binding_resolver.resolve(
                    node, session.output_store, **context
                )
                if node.permission_requirement == PermissionRequirement.RESTRICTED:
                    return self.fail(graph, session, node, "Restricted capability", correlation_id)
                if (
                    node.permission_requirement == PermissionRequirement.CONFIRM_REQUIRED
                    and node.node_id not in confirmed
                    and not self.permission_gate(node, inputs)
                ):
                    record.state = NodeExecutionState.WAITING_FOR_PERMISSION
                    record.resolved_inputs = inputs
                    session.state = GraphExecutionState.WAITING_FOR_PERMISSION
                    session.set_waiting_reason(
                        ExecutionWaitingReason.WAITING_FOR_PERMISSION,
                        node_id=node.node_id,
                    )
                    session.permission_wait_started_at = session.waiting_since
                    session.append_timeline("permission_required", node.node_id)
                    self.checkpoint_store.save(session)
                    return GraphExecutionResult(
                        session,
                        self.collect_graph_outputs(graph, session),
                        requires_permission=True,
                        pending_node_ids=(node.node_id,),
                    )
                try:
                    if (
                        node.permission_requirement
                        == PermissionRequirement.CONFIRM_REQUIRED
                    ):
                        inputs["_confirmed"] = True
                    self.run_node(session, node, inputs, correlation_id)
                except ReliableExecutionFailure as error:
                    if (
                        self.replan_enabled
                        and error.recommended_action
                        in {
                            RecommendedAction.REPLAN,
                            RecommendedAction.REQUEST_USER_INPUT,
                        }
                    ):
                        trigger = ReplanTrigger.from_failure(
                            node_id=node.node_id,
                            category=error.error_category,
                            session=session,
                            evidence=(error.error_category.value,),
                            user_input_required=(
                                error.recommended_action
                                == RecommendedAction.REQUEST_USER_INPUT
                            ),
                        )
                        session.state = (
                            GraphExecutionState.NEEDS_USER_INPUT
                            if trigger.user_input_required
                            else GraphExecutionState.REPLANNING
                        )
                        session.append_timeline(
                            "replan_requested",
                            node.node_id,
                            reason=trigger.reason,
                        )
                        self.checkpoint_store.save(session)
                        self.emit_node(
                            "runtime.execution.replan_requested",
                            session,
                            node,
                            correlation_id,
                            replan_reason=trigger.reason,
                        )
                        return GraphExecutionResult(
                            session,
                            self.collect_graph_outputs(graph, session),
                            error=str(error),
                            requires_replan=True,
                            replan_trigger=trigger,
                        )
                    return self.fail(
                        graph,
                        session,
                        node,
                        str(error),
                        correlation_id,
                        outcome=error.outcome,
                    )
                except Exception as error:
                    return self.fail(graph, session, node, str(error), correlation_id)
                self.checkpoint_store.save(session)
                progressed = True
            if not progressed:
                return self.fail(graph, session, None, "No executable node remains.", correlation_id)

        self.emit_session(
            "runtime.execution.goal_verification_started",
            session,
            correlation_id,
        )
        goal_result = self.goal_verifier.verify(
            goal,
            success_criteria_mappings,
            session,
            {
                node_id: record.verification_result
                for node_id, record in session.node_records.items()
                if record.verification_result is not None
            },
        )
        self.emit_session(
            "runtime.execution.goal_verification_completed",
            session,
            correlation_id,
            goal_verification_status=goal_result.status.value,
        )
        if goal_result.status == VerificationStatus.FAILED:
            return self.fail(
                graph,
                session,
                None,
                "Goal verification failed.",
                correlation_id,
                outcome=ExecutionOutcome.VERIFICATION_FAILED,
                goal_verification_status=goal_result.status,
            )
        if goal_result.status == VerificationStatus.INCONCLUSIVE:
            if not graph.execution_policy.allow_partial_completion:
                return self.fail(
                    graph,
                    session,
                    None,
                    "Optional goal criteria were not satisfied.",
                    correlation_id,
                    outcome=ExecutionOutcome.VERIFICATION_FAILED,
                    goal_verification_status=goal_result.status,
                )
            session.state = GraphExecutionState.PARTIALLY_COMPLETED
            execution_outcome = ExecutionOutcome.PARTIAL
        else:
            session.state = GraphExecutionState.SUCCEEDED
            execution_outcome = ExecutionOutcome.SUCCEEDED
        session.clear_waiting_reason()
        session.completed_at = datetime.now(timezone.utc)
        session.append_timeline("session_completed")
        graph_outputs = self.collect_graph_outputs(graph, session)
        session.summary = ExecutionSummary.create(
            graph,
            session,
            graph_outputs,
            outcome=execution_outcome,
            goal_verification_status=goal_result.status,
        )
        self.checkpoint_store.save(session)
        self.emit_session(
            "runtime.execution.session_completed",
            session,
            correlation_id,
            execution_summary=session.summary.to_dict(),
        )
        return GraphExecutionResult(
            session,
            graph_outputs,
            summary=session.summary,
        )

    def node_decision(self, graph, session, node):
        incoming = [
            edge for edge in graph.edges if edge.target_node_id == node.node_id
        ]
        if not incoming:
            return "run"
        for edge in incoming:
            source_state = session.node_records[edge.source_node_id].state
            if source_state in {
                NodeExecutionState.PENDING,
                NodeExecutionState.READY,
                NodeExecutionState.RUNNING,
                NodeExecutionState.WAITING_FOR_PERMISSION,
                NodeExecutionState.WAITING_FOR_PROVIDER,
                NodeExecutionState.VERIFICATION_PENDING,
                NodeExecutionState.RETRY_PENDING,
                NodeExecutionState.RETRYING,
            }:
                return "wait"
            if source_state in {NodeExecutionState.FAILED, NodeExecutionState.CANCELLED}:
                return "skip"
            if edge.edge_type in {
                EdgeType.CONDITIONAL_TRUE,
                EdgeType.CONDITIONAL_FALSE,
            }:
                if source_state == NodeExecutionState.SKIPPED:
                    return "skip"
                matched = bool(
                    session.output_store.get(edge.source_node_id, "result").value
                )
                expected = edge.edge_type == EdgeType.CONDITIONAL_TRUE
                if matched != expected:
                    return "skip"
            elif source_state == NodeExecutionState.SKIPPED:
                return "skip"
        return "run"

    def run_node(self, session, node, inputs, correlation_id):
        record = session.node_records[node.node_id]
        record.resolved_inputs = dict(inputs)
        record.idempotency_key = record.idempotency_key or idempotency_key(
            session.goal_id, session.graph_version, node.node_id
        )
        attempt_number = len(record.attempt_history) + 1
        use_fallback_provider = False
        while True:
            is_retry = attempt_number > 1
            record.state = (
                NodeExecutionState.RETRYING
                if is_retry
                else NodeExecutionState.RUNNING
            )
            session.append_timeline(
                "node_retry_started" if is_retry else "node_started",
                node.node_id,
                attempt_number=attempt_number,
            )
            record.started_at = session.updated_at
            self.emit_node(
                (
                    "runtime.execution.retry_started"
                    if is_retry
                    else "runtime.execution.node_started"
                ),
                session,
                node,
                correlation_id,
                attempt_number=attempt_number,
            )
            attempt_started = datetime.now(timezone.utc)
            error = None
            outputs = {}
            verification = None
            try:
                attempt_inputs = dict(inputs)
                attempt_inputs["_idempotency_key"] = record.idempotency_key
                attempt_inputs["_use_fallback_provider"] = (
                    use_fallback_provider
                )
                if node.node_type == NodeType.CONDITION:
                    raw_outputs = evaluate_condition(attempt_inputs)
                elif node.node_type in {
                    NodeType.TRANSFORM,
                    NodeType.RESULT,
                    NodeType.NO_OP,
                }:
                    raw_outputs = execute_system_node(node, attempt_inputs)
                else:
                    session.provider_calls += 1
                    record.state = NodeExecutionState.WAITING_FOR_PROVIDER
                    session.set_waiting_reason(
                        ExecutionWaitingReason.WAITING_FOR_PROVIDER,
                        node_id=node.node_id,
                    )
                    self.checkpoint_store.save(session)
                    try:
                        raw_outputs = self.capability_adapter.execute(
                            node, attempt_inputs
                        )
                    finally:
                        session.clear_waiting_reason(node_id=node.node_id)
                        record.state = NodeExecutionState.RUNNING
                outputs = normalize_outputs(node, raw_outputs)
                record.state = NodeExecutionState.VERIFICATION_PENDING
                session.append_timeline(
                    "node_verification_started",
                    node.node_id,
                    attempt_number=attempt_number,
                )
                self.emit_node(
                    "runtime.execution.verification_started",
                    session,
                    node,
                    correlation_id,
                    attempt_number=attempt_number,
                )
                if self.verification_enabled:
                    if (
                        node.verification_policy.verification_level.value
                        == "ExternalReadBack"
                    ):
                        session.provider_calls += 1
                    verification = self.node_result_verifier.verify(
                        node,
                        inputs,
                        outputs,
                        adapter=self.capability_adapter,
                    )
                else:
                    from jarvis.native_task_graph import VerificationLevel
                    from .reliability import VerificationResult

                    verification = VerificationResult(
                        VerificationStatus.SKIPPED,
                        VerificationLevel.NONE,
                        1.0,
                        evidence=("verification_feature_disabled",),
                    )
                record.verification_result = verification
            except Exception as caught:
                error = caught
            attempt_completed = datetime.now(timezone.utc)
            category = classify_error(error) if error else ErrorCategory.NONE
            if error is None and verification and not verification.is_successful:
                session.verification_failures += 1
                verification_code = verification.diagnostics.get(
                    "verificationCode", ""
                )
                if verification_code == "multiple_candidates":
                    record.pending_outputs = dict(outputs)
                category = {
                    "not_found": ErrorCategory.NOT_FOUND,
                    "multiple_candidates": ErrorCategory.MULTIPLE_CANDIDATES,
                    "schema_violation": ErrorCategory.SCHEMA_VIOLATION,
                }.get(
                    verification_code,
                    (
                        ErrorCategory.SCHEMA_VIOLATION
                        if verification.verification_level.value == "Schema"
                        else ErrorCategory.SEMANTIC_MISMATCH
                    ),
                )
            decision = self.retry_controller.decide(
                policy=node.retry_policy,
                attempt_number=attempt_number,
                error_category=category,
                error_code=str(getattr(error, "code", "")),
                verification_result=verification,
                external_mutation=(
                    node.permission_requirement
                    != PermissionRequirement.SAFE
                ),
            )
            record.attempt_history.append(
                AttemptRecord(
                    attempt_number,
                    str(node.metadata.get("providerId", "")),
                    attempt_started,
                    attempt_completed,
                    max(
                        0.0,
                        (attempt_completed - attempt_started).total_seconds(),
                    ),
                    "Succeeded" if error is None else "Failed",
                    category,
                    str(getattr(error, "code", "")),
                    decision.should_retry,
                    (
                        verification.status
                        if verification
                        else VerificationStatus.SKIPPED
                    ),
                    record.idempotency_key,
                    safe_hash(outputs) if outputs else "",
                )
            )
            if error is None and verification and verification.is_successful:
                for key, definition in node.outputs.items():
                    if key in outputs:
                        session.output_store.put(
                            TypedOutput(
                                node.node_id,
                                key,
                                definition.value_type,
                                outputs[key],
                            )
                        )
                record.state = NodeExecutionState.SUCCEEDED
                session.append_timeline(
                    "node_verification_passed",
                    node.node_id,
                    attempt_number=attempt_number,
                )
                self.emit_node(
                    "runtime.execution.verification_passed",
                    session,
                    node,
                    correlation_id,
                    attempt_number=attempt_number,
                )
                if is_retry:
                    session.append_timeline(
                        "node_retry_completed",
                        node.node_id,
                        attempt_number=attempt_number,
                    )
                    self.emit_node(
                        "runtime.execution.retry_completed",
                        session,
                        node,
                        correlation_id,
                        attempt_number=attempt_number,
                    )
                session.append_timeline("node_completed", node.node_id)
                record.completed_at = session.updated_at
                self.emit_node(
                    "runtime.execution.node_completed",
                    session,
                    node,
                    correlation_id,
                    attempt_number=attempt_number,
                )
                return
            record.state = NodeExecutionState.VERIFICATION_FAILED
            session.append_timeline(
                "node_verification_failed",
                node.node_id,
                attempt_number=attempt_number,
                error_category=category.value,
            )
            self.emit_node(
                "runtime.execution.verification_failed",
                session,
                node,
                correlation_id,
                attempt_number=attempt_number,
                error_category=category.value,
            )
            if self.retry_enabled and decision.should_retry:
                session.retry_count += 1
                record.state = NodeExecutionState.RETRY_PENDING
                session.state = GraphExecutionState.WAITING_FOR_RETRY
                session.set_waiting_reason(
                    ExecutionWaitingReason.WAITING_FOR_RETRY,
                    node_id=node.node_id,
                )
                session.append_timeline(
                    "node_retry_scheduled",
                    node.node_id,
                    attempt_number=decision.attempt_number,
                    delay_seconds=decision.delay_seconds,
                )
                self.emit_node(
                    "runtime.execution.retry_scheduled",
                    session,
                    node,
                    correlation_id,
                    attempt_number=decision.attempt_number,
                    delay_seconds=decision.delay_seconds,
                )
                self.checkpoint_store.save(session)
                self.sleeper(decision.delay_seconds)
                session.clear_waiting_reason(node_id=node.node_id)
                session.state = GraphExecutionState.RUNNING
                attempt_number = decision.attempt_number
                use_fallback_provider = decision.use_fallback_provider
                continue
            if self.retry_enabled and decision.exhausted:
                session.append_timeline(
                    "node_retry_exhausted",
                    node.node_id,
                    attempt_number=attempt_number,
                )
                self.emit_node(
                    "runtime.execution.retry_exhausted",
                    session,
                    node,
                    correlation_id,
                    attempt_number=attempt_number,
                )
                raise ReliableExecutionFailure(
                    str(error or "Node verification failed."),
                    ExecutionOutcome.RETRY_EXHAUSTED,
                    error_category=category,
                )
            raise ReliableExecutionFailure(
                str(
                    error
                    or "; ".join(verification.problems)
                    or "Node verification failed."
                ),
                (
                    ExecutionOutcome.VERIFICATION_FAILED
                    if verification is not None
                    else ExecutionOutcome.FAILED
                ),
                error_category=category,
                recommended_action=(
                    verification.recommended_action
                    if verification is not None
                    else (
                        RecommendedAction.REPLAN
                        if category
                        in {
                            ErrorCategory.NOT_FOUND,
                            ErrorCategory.MULTIPLE_CANDIDATES,
                            ErrorCategory.SEMANTIC_MISMATCH,
                        }
                        else None
                    )
                ),
            )

    def skip_node(self, session, node, correlation_id):
        record = session.node_records[node.node_id]
        record.state = NodeExecutionState.SKIPPED
        session.append_timeline("node_skipped", node.node_id)
        self.emit_node("runtime.execution.node_skipped", session, node, correlation_id)
        self.checkpoint_store.save(session)

    def fail(
        self,
        graph,
        session,
        node,
        error,
        correlation_id,
        *,
        outcome=ExecutionOutcome.FAILED,
        goal_verification_status=VerificationStatus.SKIPPED,
    ):
        error_category = classify_error(RuntimeError(error))
        if node is not None:
            record = session.node_records[node.node_id]
            record.state = NodeExecutionState.FAILED
            record.error = error_category.value
        session.state = GraphExecutionState.FAILED
        session.clear_waiting_reason(
            node_id=getattr(node, "node_id", "")
        )
        session.completed_at = datetime.now(timezone.utc)
        session.append_timeline(
            "session_failed",
            getattr(node, "node_id", ""),
            error_category=error_category.value,
        )
        graph_outputs = self.collect_graph_outputs(graph, session)
        session.summary = ExecutionSummary.create(
            graph,
            session,
            graph_outputs,
            outcome=outcome,
            goal_verification_status=goal_verification_status,
        )
        self.checkpoint_store.save(session)
        self.emit_session(
            "runtime.execution.session_completed",
            session,
            correlation_id,
            error_category=error_category.value,
            execution_summary=session.summary.to_dict(),
        )
        return GraphExecutionResult(
            session,
            graph_outputs,
            error=error,
            summary=session.summary,
        )

    def collect_graph_outputs(self, graph, session):
        values = {}
        for output in graph.outputs:
            if session.output_store.has(output.source_node_id, output.source_output_key):
                values[output.output_id] = session.output_store.get(
                    output.source_node_id, output.source_output_key
                ).value
        return values

    def collect_graph_outputs_from_store(self, session):
        return {}

    def emit_node(
        self,
        event_type,
        session,
        node,
        correlation_id,
        **extra,
    ):
        attempt_number = extra.pop(
            "attempt_number",
            len(session.node_records[node.node_id].attempt_history),
        )
        self.emit(
            event_type,
            session.session_id,
            correlation_id,
            session_id=session.session_id,
            session_version=session.session_version,
            snapshot_id=session.snapshot_id,
            graph_id=session.graph_id,
            node_id=node.node_id,
            node_state=session.node_records[node.node_id].state.value,
            goal_execution_id=session.goal_execution_id,
            retry_count=session.retry_count,
            replan_count=session.replan_count,
            attempt_number=attempt_number,
            **extra,
        )

    def emit_session(self, event_type, session, correlation_id, **extra):
        attempt_number = extra.pop("attempt_number", 0)
        self.emit(
            event_type,
            session.session_id,
            correlation_id,
            session_id=session.session_id,
            session_version=session.session_version,
            goal_execution_id=session.goal_execution_id,
            snapshot_id=session.snapshot_id,
            graph_id=session.graph_id,
            session_state=session.state.value,
            waiting_reason=session.waiting_reason.value,
            waiting_since=(
                session.waiting_since.isoformat()
                if session.waiting_since
                else None
            ),
            started_at=(
                session.started_at.isoformat()
                if session.started_at
                else None
            ),
            completed_at=(
                session.completed_at.isoformat()
                if session.completed_at
                else None
            ),
            duration_seconds=session.duration_seconds,
            retry_count=session.retry_count,
            replan_count=session.replan_count,
            attempt_number=attempt_number,
            **extra,
        )

    def emit(self, event_type, aggregate_id, correlation_id, **payload):
        if self.event_bus is None:
            return
        self.event_bus.publish(
            BaseEvent(
                event_type=event_type,
                aggregate_type="GraphExecutionSession",
                aggregate_id=aggregate_id,
                payload=payload,
                correlation_id=correlation_id,
            )
        )


def normalize_outputs(node, raw):
    if isinstance(raw, dict):
        values = dict(raw)
    elif is_dataclass(raw):
        values = asdict(raw)
        values["_object"] = raw
    else:
        values = {}
    if len(node.outputs) == 1:
        key = next(iter(node.outputs))
        if key == "event" and hasattr(raw, "events"):
            events = list(getattr(raw, "events", ()) or ())
            values[key] = events[0] if events else raw
        elif key == "reminder" and hasattr(raw, "reminders"):
            reminders = list(getattr(raw, "reminders", ()) or ())
            values[key] = reminders[0] if reminders else raw
        elif key not in values:
            values[key] = raw
        elif key in {"forecast", "message"}:
            values[key] = raw
    if "events" in node.outputs and hasattr(raw, "events"):
        values["events"] = raw.events
    if "contacts" in node.outputs and hasattr(raw, "contacts"):
        values["contacts"] = raw.contacts
    return values


def execute_system_node(node, inputs):
    if node.node_type == NodeType.RESULT:
        value = inputs.get("source", inputs.get("message", inputs))
        return {"result": natural_language(value)}
    source = inputs.get("source")
    return {"result": natural_language(source)}


def natural_language(value):
    if hasattr(value, "to_natural_language"):
        return value.to_natural_language()
    if isinstance(value, (list, tuple)):
        return "\n".join(natural_language(item) for item in value)
    return str(value)


def evaluate_condition(inputs):
    source = inputs.get("value")
    expression = str(inputs.get("expression", "")).strip()
    actual, symbol, expected = parse_condition(source, expression)
    operations = {
        ">": operator.gt,
        ">=": operator.ge,
        "<": operator.lt,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
    }
    matched = bool(operations[symbol](actual, expected))
    return {
        "result": matched,
        "matched_branch": "true" if matched else "false",
        "evidence": {
            "expression": expression,
            "actual": actual,
            "expected": expected,
            "operator": symbol,
        },
        "actual_value": actual,
        "expected_value": expected,
        "operator": symbol,
    }


def parse_condition(source, expression):
    match = re.fullmatch(
        r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*",
        expression,
    )
    if not match:
        raise ValueError(f"Unsupported condition expression: {expression}")
    field, symbol, expected_text = match.groups()
    aliases = {
        "rain_probability": (
            "rain_probability",
            "precipitation_probability",
        )
    }
    actual = None
    for candidate in aliases.get(field, (field,)):
        if isinstance(source, dict) and candidate in source:
            actual = source[candidate]
            break
        if hasattr(source, candidate):
            actual = getattr(source, candidate)
            break
    if actual is None:
        raise ValueError(f"Condition field not found: {field}")
    expected = float(expected_text)
    return float(actual), symbol, expected
