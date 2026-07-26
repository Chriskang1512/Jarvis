from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from uuid import uuid4


class TaskState(Enum):
    """Runtime task lifecycle states."""

    PENDING = "PENDING"
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    OPTIMIZING = "OPTIMIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    RETRYING = "RETRYING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    WAIT_EXTERNAL = "WAIT_EXTERNAL"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUCCESS = "SUCCESS"


class TransitionSource(str, Enum):
    """Actor category responsible for a task state transition."""

    SYSTEM = "SYSTEM"
    USER = "USER"
    RECOVERY = "RECOVERY"
    EVENT = "EVENT"


@dataclass(frozen=True)
class PendingQuestion:
    """One Runtime-owned question waiting for a user answer."""

    kind: str = ""
    text: str = ""
    payload: dict = field(default_factory=dict)
    turns_remaining: int = 0
    expires_at: float = 0.0


@dataclass(frozen=True)
class PendingArtifact:
    """A draft or selection frozen at a conversation boundary."""

    artifact_type: str
    artifact_id: str
    fingerprint: str
    created_at: str
    verified: bool = False
    payload: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ClarificationTurn:
    """Privacy-safe record of a clarification exchange."""

    question_kind: str
    answer_kind: str = ""
    occurred_at: str = ""


@dataclass(frozen=True)
class ConversationContext:
    """All transient conversation state owned by one RuntimeTask."""

    task_id: str = ""
    goal: str = ""
    current_step: int = 0
    pending_question: PendingQuestion | None = None
    pending_answer: str = ""
    clarification_history: tuple[ClarificationTurn, ...] = ()
    selected_entities: dict = field(default_factory=dict)
    pending_artifacts: tuple[PendingArtifact, ...] = ()
    confirmation_state: str = ""
    expires_at: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, "clarification_history", tuple(self.clarification_history))
        object.__setattr__(self, "selected_entities", dict(self.selected_entities))
        object.__setattr__(self, "pending_artifacts", tuple(self.pending_artifacts))


@dataclass(frozen=True)
class StateTransitionRecord:
    """Privacy-safe record of one RuntimeTask state change."""

    transition_id: int
    from_state: TaskState
    to_state: TaskState
    transition_reason: str = ""
    transition_source: TransitionSource = TransitionSource.SYSTEM
    wall_clock_ms: int = 0
    waiting_ms: int = 0
    active_execution_ms: int = 0
    step_id: str = ""
    occurred_at: str = ""

    @property
    def sequence(self):
        """Backward-compatible transition ordering alias."""
        return self.transition_id

    @property
    def reason(self):
        """Backward-compatible reason alias."""
        return self.transition_reason

    @property
    def duration_ms(self):
        """Backward-compatible wall-clock duration alias."""
        return self.wall_clock_ms


@dataclass(frozen=True)
class TaskStepRecord:
    """Execution record for one task step."""

    step_index: int
    tool_name: str
    action: str = ""
    status: TaskState = TaskState.PENDING
    attempts: int = 0
    response: str = ""
    error: str = ""
    failure_reason: str = ""
    validator: str = ""
    field: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class RuntimeTask:
    """A stateful execution wrapper around one ExecutionPlan."""

    id: str
    goal: str
    status: TaskState = TaskState.PENDING
    created_at: str = ""
    updated_at: str = ""
    current_step: int = 0
    completed_steps: tuple[int, ...] = ()
    failed_steps: tuple[int, ...] = ()
    retry_count: int = 0
    step_records: tuple[TaskStepRecord, ...] = ()
    transition_history: tuple[StateTransitionRecord, ...] = ()
    trace_id: str = ""
    correlation_id: str = ""
    checkpoint_version: int = 1
    step_input_fingerprint: str = ""
    external_operation_id: str = ""
    confirmation_state: str = ""
    draft_version: int = 0
    permission_snapshot: str = ""
    conversation_context: ConversationContext | None = None
    duration_ms: int = 0

    def __post_init__(self):
        """Fill stable IDs and timestamps."""
        now = now_iso()

        if self.id == "":
            object.__setattr__(self, "id", create_task_id())

        if self.created_at == "":
            object.__setattr__(self, "created_at", now)

        if self.updated_at == "":
            object.__setattr__(self, "updated_at", self.created_at)

        object.__setattr__(self, "completed_steps", tuple(self.completed_steps))
        object.__setattr__(self, "failed_steps", tuple(self.failed_steps))
        object.__setattr__(self, "step_records", tuple(self.step_records))
        object.__setattr__(self, "transition_history", tuple(self.transition_history))
        if self.conversation_context is None:
            object.__setattr__(
                self,
                "conversation_context",
                ConversationContext(task_id=self.id, goal=self.goal, current_step=self.current_step),
            )

    def transition(
        self,
        status,
        reason="legacy_runtime",
        source=TransitionSource.SYSTEM,
        **changes,
    ):
        """Route state changes through the single transition validator."""
        from jarvis.runtime.task.state_machine import transition_task

        return transition_task(
            self,
            status,
            reason=reason,
            source=source,
            changes=changes,
        )

    def to_dict(self):
        """Return a diagnostics-friendly dictionary."""
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_step": self.current_step,
            "completed_steps": list(self.completed_steps),
            "failed_steps": list(self.failed_steps),
            "retry_count": self.retry_count,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "checkpoint_version": self.checkpoint_version,
            "step_input_fingerprint": self.step_input_fingerprint,
            "external_operation_id": self.external_operation_id,
            "confirmation_state": self.confirmation_state,
            "draft_version": self.draft_version,
            "permission_snapshot": self.permission_snapshot,
            "conversation_context": conversation_context_to_dict(self.conversation_context),
            "duration_ms": self.duration_ms,
            "transition_history": [
                {
                    "transition_id": record.transition_id,
                    "from_state": record.from_state.value,
                    "to_state": record.to_state.value,
                    "transition_reason": record.transition_reason,
                    "transition_source": record.transition_source.value,
                    "wall_clock_ms": record.wall_clock_ms,
                    "waiting_ms": record.waiting_ms,
                    "active_execution_ms": record.active_execution_ms,
                    "step_id": record.step_id,
                    "occurred_at": record.occurred_at,
                }
                for record in self.transition_history
            ],
            "step_records": [
                {
                    "step_index": record.step_index,
                    "tool_name": record.tool_name,
                    "action": record.action,
                    "status": record.status.value,
                    "attempts": record.attempts,
                    "response": record.response,
                    "error": record.error,
                    "failure_reason": record.failure_reason,
                    "validator": record.validator,
                    "field": record.field,
                    "started_at": record.started_at,
                    "completed_at": record.completed_at,
                    "duration_ms": record.duration_ms,
                }
                for record in self.step_records
            ],
        }


def create_task_id():
    """Return a compact task ID."""
    return f"RT-{uuid4().hex[:8].upper()}"


def now_iso():
    """Return local timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def conversation_context_to_dict(context):
    """Return privacy-safe conversation diagnostics without artifact payloads."""
    if context is None:
        return None
    question = context.pending_question
    return {
        "task_id": context.task_id,
        "goal": context.goal,
        "current_step": context.current_step,
        "pending_question": (
            {
                "kind": question.kind,
                "text": question.text,
                "turns_remaining": question.turns_remaining,
                "expires_at": question.expires_at,
            }
            if question is not None
            else None
        ),
        "clarification_history": [
            {
                "question_kind": item.question_kind,
                "answer_kind": item.answer_kind,
                "occurred_at": item.occurred_at,
            }
            for item in context.clarification_history
        ],
        "selected_entity_keys": sorted(context.selected_entities),
        "pending_artifacts": [
            {
                "artifact_type": item.artifact_type,
                "artifact_id": item.artifact_id,
                "fingerprint": item.fingerprint,
                "created_at": item.created_at,
                "verified": item.verified,
            }
            for item in context.pending_artifacts
        ],
        "confirmation_state": context.confirmation_state,
        "expires_at": context.expires_at,
    }
