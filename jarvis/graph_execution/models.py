"""Mutable runtime state for executing an immutable NativeTaskGraph."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any
from uuid import uuid4

from .reliability import (
    AttemptRecord,
    ExecutionOutcome,
    VerificationResult,
    VerificationStatus,
)


CURRENT_SESSION_VERSION = 2


def utc_now():
    return datetime.now(timezone.utc)


class NodeExecutionState(str, Enum):
    PENDING = "Pending"
    READY = "Ready"
    WAITING_FOR_PERMISSION = "WaitingForPermission"
    WAITING_FOR_PROVIDER = "WaitingForProvider"
    VERIFICATION_PENDING = "VerificationPending"
    VERIFICATION_FAILED = "VerificationFailed"
    RETRY_PENDING = "RetryPending"
    RETRYING = "Retrying"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    CANCELLED = "Cancelled"


class GraphExecutionState(str, Enum):
    CREATED = "Created"
    WAITING_FOR_PERMISSION = "WaitingForPermission"
    WAITING_FOR_RETRY = "WaitingForRetry"
    NEEDS_USER_INPUT = "NeedsUserInput"
    REPLANNING = "Replanning"
    PARTIALLY_COMPLETED = "PartiallyCompleted"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class ExecutionWaitingReason(str, Enum):
    NONE = "None"
    WAITING_FOR_CLARIFICATION = "WaitingForClarification"
    WAITING_FOR_PERMISSION = "WaitingForPermission"
    WAITING_FOR_PROVIDER = "WaitingForProvider"
    WAITING_FOR_RETRY = "WaitingForRetry"


@dataclass(frozen=True)
class TypedOutput:
    node_id: str
    output_key: str
    value_type: str
    value: Any
    created_at: datetime = field(default_factory=utc_now)


class OutputStore:
    def __init__(self):
        self._values = {}

    def put(self, output):
        key = (output.node_id, output.output_key)
        if key in self._values:
            raise ValueError(f"Output already exists: {output.node_id}.{output.output_key}")
        self._values[key] = output

    def get(self, node_id, output_key):
        try:
            return self._values[(node_id, output_key)]
        except KeyError as error:
            raise KeyError(f"Output not found: {node_id}.{output_key}") from error

    def has(self, node_id, output_key):
        return (node_id, output_key) in self._values

    def values(self):
        return tuple(self._values.values())

    def to_dict(self):
        return {
            f"{node_id}.{key}": {
                "nodeId": value.node_id,
                "outputKey": value.output_key,
                "valueType": value.value_type,
                "value": checkpoint_value(value.value),
                "createdAt": value.created_at.isoformat(),
            }
            for (node_id, key), value in self._values.items()
        }

    @classmethod
    def from_dict(cls, values):
        store = cls()
        for item in dict(values or {}).values():
            store.put(
                TypedOutput(
                    node_id=str(item["nodeId"]),
                    output_key=str(item["outputKey"]),
                    value_type=str(item["valueType"]),
                    value=item.get("value"),
                    created_at=datetime.fromisoformat(
                        str(item["createdAt"]).replace("Z", "+00:00")
                    ),
                )
            )
        return store


@dataclass(frozen=True)
class TimelineEntry:
    event_type: str
    occurred_at: datetime
    node_id: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class NodeExecutionRecord:
    node_id: str
    state: NodeExecutionState = NodeExecutionState.PENDING
    resolved_inputs: dict = field(default_factory=dict)
    error: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_history: list[AttemptRecord] = field(default_factory=list)
    verification_result: VerificationResult | None = None
    idempotency_key: str = ""
    # Runtime-only values needed to resolve an inconclusive result. They are
    # deliberately excluded from checkpoints because they may contain PII.
    pending_outputs: dict = field(default_factory=dict, repr=False)


@dataclass
class GraphExecutionSession:
    graph_id: str
    graph_version: int
    goal_id: str
    snapshot_id: str
    goal_execution_id: str = field(
        default_factory=lambda: f"goal-execution-{uuid4()}"
    )
    session_version: int = CURRENT_SESSION_VERSION
    session_id: str = field(default_factory=lambda: f"execution-{uuid4()}")
    state: GraphExecutionState = GraphExecutionState.CREATED
    waiting_reason: ExecutionWaitingReason = ExecutionWaitingReason.NONE
    waiting_since: datetime | None = None
    node_records: dict[str, NodeExecutionRecord] = field(default_factory=dict)
    output_store: OutputStore = field(default_factory=OutputStore)
    timeline: list[TimelineEntry] = field(default_factory=list)
    checkpoint_revision: int = 0
    provider_calls: int = 0
    retry_count: int = 0
    replan_count: int = 0
    verification_failures: int = 0
    previous_session_ids: tuple[str, ...] = ()
    recovery_path: tuple[str, ...] = ()
    final_graph_id: str = ""
    permission_wait_started_at: datetime | None = None
    permission_wait_seconds: float = 0.0
    summary: "ExecutionSummary | None" = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utc_now)

    def __setattr__(self, name, value):
        if name == "snapshot_id" and "snapshot_id" in self.__dict__:
            raise AttributeError("GraphExecutionSession.snapshot_id is immutable.")
        super().__setattr__(name, value)

    @classmethod
    def create(cls, graph, snapshot):
        session = cls(
            graph_id=graph.graph_id,
            graph_version=graph.version,
            goal_id=graph.goal_id,
            snapshot_id=snapshot.snapshot_id,
            final_graph_id=graph.graph_id,
            node_records={
                node.node_id: NodeExecutionRecord(node.node_id)
                for node in graph.nodes
            },
        )
        session.append_timeline("session_created")
        return session

    def append_timeline(self, event_type, node_id="", **details):
        now = utc_now()
        self.timeline.append(TimelineEntry(event_type, now, node_id, dict(details)))
        self.updated_at = now

    @property
    def duration_seconds(self):
        if self.started_at is None:
            return 0.0
        end = self.completed_at or utc_now()
        return max(0.0, (end - self.started_at).total_seconds())

    def set_waiting_reason(self, reason, *, node_id=""):
        reason = ExecutionWaitingReason(reason)
        if reason == ExecutionWaitingReason.NONE:
            raise ValueError("Use clear_waiting_reason() to leave a waiting state.")
        self.waiting_reason = reason
        self.waiting_since = utc_now()
        self.append_timeline(
            "session_waiting",
            node_id,
            waiting_reason=reason.value,
            waiting_since=self.waiting_since.isoformat(),
        )

    def clear_waiting_reason(self, *, node_id=""):
        previous = self.waiting_reason
        waiting_since = self.waiting_since
        self.waiting_reason = ExecutionWaitingReason.NONE
        self.waiting_since = None
        if previous != ExecutionWaitingReason.NONE:
            self.append_timeline(
                "session_waiting_cleared",
                node_id,
                waiting_reason=previous.value,
                waiting_since=(
                    waiting_since.isoformat() if waiting_since else None
                ),
            )

    @classmethod
    def from_checkpoint(cls, checkpoint, graph, snapshot):
        checkpoint = migrate_checkpoint(checkpoint)
        session_version = int(
            checkpoint.get("sessionVersion", CURRENT_SESSION_VERSION)
        )
        if session_version < 1:
            raise ValueError("Checkpoint SessionVersion must be at least 1.")
        if session_version > CURRENT_SESSION_VERSION:
            raise ValueError(
                "Checkpoint SessionVersion is newer than this runtime supports."
            )
        if str(checkpoint.get("snapshotId", "")) != snapshot.snapshot_id:
            raise ValueError("Checkpoint SnapshotId does not match the execution snapshot.")
        if (
            str(checkpoint.get("graphId", "")) != graph.graph_id
            or int(checkpoint.get("graphVersion", 0)) != graph.version
        ):
            raise ValueError("Checkpoint graph identity does not match the plan.")
        records = {}
        stored_nodes = dict(checkpoint.get("nodes", {}))
        for node in graph.nodes:
            value = dict(stored_nodes.get(node.node_id, {}))
            records[node.node_id] = NodeExecutionRecord(
                node_id=node.node_id,
                state=NodeExecutionState(
                    value.get("state", NodeExecutionState.PENDING.value)
                ),
                resolved_inputs=dict(value.get("resolvedInputs", {})),
                error=str(value.get("error", "")),
                attempt_history=[
                    AttemptRecord.from_dict(item)
                    for item in value.get("attemptHistory", ())
                ],
                verification_result=verification_result_from_dict(
                    value.get("verificationResult")
                ),
                idempotency_key=str(value.get("idempotencyKey", "")),
            )
        session = cls(
            session_id=str(checkpoint["sessionId"]),
            session_version=session_version,
            goal_execution_id=str(
                checkpoint.get(
                    "goalExecutionId",
                    f"goal-execution-{uuid4()}",
                )
            ),
            snapshot_id=snapshot.snapshot_id,
            graph_id=graph.graph_id,
            graph_version=graph.version,
            goal_id=graph.goal_id,
            state=GraphExecutionState(
                checkpoint.get("state", GraphExecutionState.CREATED.value)
            ),
            waiting_reason=ExecutionWaitingReason(
                checkpoint.get(
                    "waitingReason", ExecutionWaitingReason.NONE.value
                )
            ),
            waiting_since=(
                datetime.fromisoformat(
                    str(checkpoint["waitingSince"]).replace("Z", "+00:00")
                )
                if checkpoint.get("waitingSince")
                else None
            ),
            node_records=records,
            output_store=OutputStore.from_dict(checkpoint.get("outputs", {})),
            checkpoint_revision=int(checkpoint.get("checkpointRevision", 0)),
            provider_calls=int(checkpoint.get("providerCalls", 0)),
            retry_count=int(checkpoint.get("retryCount", 0)),
            replan_count=int(checkpoint.get("replanCount", 0)),
            verification_failures=int(
                checkpoint.get("verificationFailures", 0)
            ),
            previous_session_ids=tuple(
                checkpoint.get("previousSessionIds", ())
            ),
            recovery_path=tuple(checkpoint.get("recoveryPath", ())),
            final_graph_id=str(
                checkpoint.get("finalGraphId", graph.graph_id)
            ),
            permission_wait_seconds=float(
                checkpoint.get("permissionWaitSeconds", 0.0)
            ),
            created_at=datetime.fromisoformat(
                str(
                    checkpoint.get("createdAt")
                    or checkpoint["updatedAt"]
                ).replace("Z", "+00:00")
            ),
            started_at=(
                datetime.fromisoformat(
                    str(checkpoint["startedAt"]).replace("Z", "+00:00")
                )
                if checkpoint.get("startedAt")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(
                    str(checkpoint["completedAt"]).replace("Z", "+00:00")
                )
                if checkpoint.get("completedAt")
                else None
            ),
        )
        session.timeline = [
            TimelineEntry(
                event_type=str(item["eventType"]),
                occurred_at=datetime.fromisoformat(
                    str(item["occurredAt"]).replace("Z", "+00:00")
                ),
                node_id=str(item.get("nodeId", "")),
                details=dict(item.get("details", {})),
            )
            for item in checkpoint.get("timeline", ())
        ]
        session.updated_at = datetime.fromisoformat(
            str(checkpoint["updatedAt"]).replace("Z", "+00:00")
        )
        if checkpoint.get("executionSummary"):
            session.summary = ExecutionSummary.from_dict(
                checkpoint["executionSummary"]
            )
        return session

    def to_checkpoint(self):
        return {
            "sessionVersion": self.session_version,
            "sessionId": self.session_id,
            "goalExecutionId": self.goal_execution_id,
            "snapshotId": self.snapshot_id,
            "graphId": self.graph_id,
            "graphVersion": self.graph_version,
            "goalId": self.goal_id,
            "state": self.state.value,
            "waitingReason": self.waiting_reason.value,
            "waitingSince": (
                self.waiting_since.isoformat() if self.waiting_since else None
            ),
            "checkpointRevision": self.checkpoint_revision,
            "providerCalls": self.provider_calls,
            "retryCount": self.retry_count,
            "replanCount": self.replan_count,
            "verificationFailures": self.verification_failures,
            "previousSessionIds": list(self.previous_session_ids),
            "recoveryPath": list(self.recovery_path),
            "finalGraphId": self.final_graph_id,
            "permissionWaitSeconds": self.permission_wait_seconds,
            "createdAt": self.created_at.isoformat(),
            "startedAt": (
                self.started_at.isoformat() if self.started_at else None
            ),
            "completedAt": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "durationSeconds": self.duration_seconds,
            "nodes": {
                key: {
                    "state": value.state.value,
                    "resolvedInputs": dict(value.resolved_inputs),
                    "error": value.error,
                    "attemptHistory": [
                        item.to_dict() for item in value.attempt_history
                    ],
                    "verificationResult": verification_result_to_dict(
                        value.verification_result
                    ),
                    "idempotencyKey": value.idempotency_key,
                }
                for key, value in self.node_records.items()
            },
            "outputs": self.output_store.to_dict(),
            "timeline": [
                {
                    "eventType": item.event_type,
                    "occurredAt": item.occurred_at.isoformat(),
                    "nodeId": item.node_id,
                    "details": dict(item.details),
                }
                for item in self.timeline
            ],
            "updatedAt": self.updated_at.isoformat(),
            "executionSummary": self.summary.to_dict()
            if self.summary
            else None,
        }


@dataclass(frozen=True)
class GraphExecutionResult:
    session: GraphExecutionSession
    graph_outputs: dict
    requires_permission: bool = False
    pending_node_ids: tuple[str, ...] = ()
    error: str = ""
    summary: "ExecutionSummary | None" = None
    requires_replan: bool = False
    replan_trigger: Any = None


@dataclass(frozen=True)
class ExecutionSummary:
    session_id: str
    snapshot_id: str
    duration_seconds: float
    succeeded_nodes: tuple[str, ...]
    skipped_nodes: tuple[str, ...]
    failed_nodes: tuple[str, ...]
    permission_wait_seconds: float
    provider_calls: int
    artifacts: tuple[dict, ...]
    result_hash: str
    outcome: ExecutionOutcome = ExecutionOutcome.SUCCEEDED
    retry_count: int = 0
    replan_count: int = 0
    verification_failures: int = 0
    final_graph_id: str = ""
    previous_session_ids: tuple[str, ...] = ()
    recovery_path: tuple[str, ...] = ()
    goal_verification_status: VerificationStatus = VerificationStatus.SKIPPED

    def to_dict(self):
        return {
            "sessionId": self.session_id,
            "snapshotId": self.snapshot_id,
            "durationSeconds": self.duration_seconds,
            "succeededNodes": list(self.succeeded_nodes),
            "skippedNodes": list(self.skipped_nodes),
            "failedNodes": list(self.failed_nodes),
            "permissionWaitSeconds": self.permission_wait_seconds,
            "providerCalls": self.provider_calls,
            "artifacts": [dict(item) for item in self.artifacts],
            "resultHash": self.result_hash,
            "outcome": self.outcome.value,
            "retryCount": self.retry_count,
            "replanCount": self.replan_count,
            "verificationFailures": self.verification_failures,
            "finalGraphId": self.final_graph_id,
            "previousSessionIds": list(self.previous_session_ids),
            "recoveryPath": list(self.recovery_path),
            "goalVerificationStatus": self.goal_verification_status.value,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            session_id=str(value["sessionId"]),
            snapshot_id=str(value["snapshotId"]),
            duration_seconds=float(value.get("durationSeconds", 0.0)),
            succeeded_nodes=tuple(value.get("succeededNodes", ())),
            skipped_nodes=tuple(value.get("skippedNodes", ())),
            failed_nodes=tuple(value.get("failedNodes", ())),
            permission_wait_seconds=float(
                value.get("permissionWaitSeconds", 0.0)
            ),
            provider_calls=int(value.get("providerCalls", 0)),
            artifacts=tuple(
                dict(item) for item in value.get("artifacts", ())
            ),
            result_hash=str(value["resultHash"]),
            outcome=ExecutionOutcome(
                value.get("outcome", ExecutionOutcome.SUCCEEDED.value)
            ),
            retry_count=int(value.get("retryCount", 0)),
            replan_count=int(value.get("replanCount", 0)),
            verification_failures=int(
                value.get("verificationFailures", 0)
            ),
            final_graph_id=str(value.get("finalGraphId", "")),
            previous_session_ids=tuple(
                value.get("previousSessionIds", ())
            ),
            recovery_path=tuple(value.get("recoveryPath", ())),
            goal_verification_status=VerificationStatus(
                value.get(
                    "goalVerificationStatus",
                    VerificationStatus.SKIPPED.value,
                )
            ),
        )

    @classmethod
    def create(
        cls,
        graph,
        session,
        graph_outputs,
        *,
        outcome=ExecutionOutcome.SUCCEEDED,
        goal_verification_status=VerificationStatus.SKIPPED,
    ):
        artifacts = []
        for node in graph.nodes:
            for key, definition in node.outputs.items():
                if (
                    definition.artifact_type
                    and session.output_store.has(node.node_id, key)
                ):
                    artifacts.append(
                        {
                            "nodeId": node.node_id,
                            "outputKey": key,
                            "artifactType": definition.artifact_type,
                        }
                    )
        return cls(
            session_id=session.session_id,
            snapshot_id=session.snapshot_id,
            duration_seconds=session.duration_seconds,
            succeeded_nodes=tuple(
                key
                for key, record in session.node_records.items()
                if record.state == NodeExecutionState.SUCCEEDED
            ),
            skipped_nodes=tuple(
                key
                for key, record in session.node_records.items()
                if record.state == NodeExecutionState.SKIPPED
            ),
            failed_nodes=tuple(
                key
                for key, record in session.node_records.items()
                if record.state == NodeExecutionState.FAILED
            ),
            permission_wait_seconds=session.permission_wait_seconds,
            provider_calls=session.provider_calls,
            artifacts=tuple(artifacts),
            result_hash=stable_result_hash(graph_outputs),
            outcome=outcome,
            retry_count=session.retry_count,
            replan_count=session.replan_count,
            verification_failures=session.verification_failures,
            final_graph_id=session.final_graph_id or graph.graph_id,
            previous_session_ids=tuple(session.previous_session_ids),
            recovery_path=tuple(session.recovery_path),
            goal_verification_status=goal_verification_status,
        )


def verification_result_to_dict(value):
    if value is None:
        return None
    return {
        "status": value.status.value,
        "verificationLevel": value.verification_level.value,
        "confidence": value.confidence,
        "evidence": list(value.evidence),
        "problems": list(value.problems),
        "recommendedAction": value.recommended_action.value,
        "verifiedAt": value.verified_at.isoformat(),
        "verifierType": value.verifier_type,
        "diagnostics": dict(value.diagnostics),
    }


def verification_result_from_dict(value):
    if not value:
        return None
    from .reliability import RecommendedAction
    from jarvis.native_task_graph import VerificationLevel

    return VerificationResult(
        status=VerificationStatus(value["status"]),
        verification_level=VerificationLevel(value["verificationLevel"]),
        confidence=float(value.get("confidence", 0.0)),
        evidence=tuple(value.get("evidence", ())),
        problems=tuple(value.get("problems", ())),
        recommended_action=RecommendedAction(
            value.get("recommendedAction", RecommendedAction.CONTINUE.value)
        ),
        verified_at=datetime.fromisoformat(
            str(value["verifiedAt"]).replace("Z", "+00:00")
        ),
        verifier_type=str(value.get("verifierType", "")),
        diagnostics=dict(value.get("diagnostics", {})),
    )


def migrate_checkpoint(value):
    """Upgrade older session checkpoints without mutating stored input."""
    checkpoint = dict(value)
    version = int(checkpoint.get("sessionVersion", 1))
    if version < 1:
        raise ValueError("Checkpoint SessionVersion must be at least 1.")
    if version > CURRENT_SESSION_VERSION:
        raise ValueError(
            "Checkpoint SessionVersion is newer than this runtime supports."
        )
    if version == 1:
        checkpoint.setdefault("goalExecutionId", f"goal-execution-{uuid4()}")
        checkpoint.setdefault("retryCount", 0)
        checkpoint.setdefault("replanCount", 0)
        checkpoint.setdefault("verificationFailures", 0)
        checkpoint.setdefault("previousSessionIds", [])
        checkpoint.setdefault("recoveryPath", [])
        checkpoint.setdefault("finalGraphId", checkpoint.get("graphId", ""))
        migrated_nodes = {}
        for node_id, raw in dict(checkpoint.get("nodes", {})).items():
            node = dict(raw)
            node.setdefault("attemptHistory", [])
            node.setdefault("verificationResult", None)
            node.setdefault("idempotencyKey", "")
            migrated_nodes[node_id] = node
        checkpoint["nodes"] = migrated_nodes
        checkpoint["sessionVersion"] = 2
    return checkpoint


def checkpoint_value(value):
    if is_dataclass(value):
        return checkpoint_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): checkpoint_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [checkpoint_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_dict"):
        return checkpoint_value(value.to_dict())
    return str(value)


def stable_result_hash(value):
    encoded = json.dumps(
        checkpoint_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
