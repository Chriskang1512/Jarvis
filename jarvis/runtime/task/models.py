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
class StateTransitionRecord:
    """Privacy-safe record of one RuntimeTask state change."""

    transition_id: int
    from_state: TaskState
    to_state: TaskState
    transition_reason: str = ""
    transition_source: TransitionSource = TransitionSource.SYSTEM
    wall_clock_ms: int = 0
    waiting_ms: int = 0
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
