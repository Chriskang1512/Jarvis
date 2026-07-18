from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from uuid import uuid4


class TaskState(Enum):
    """Runtime task lifecycle states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    WAIT_EXTERNAL = "WAIT_EXTERNAL"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"


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

    def transition(self, status, **changes):
        """Return a copy with an updated status."""
        return replace(self, status=status, updated_at=now_iso(), **changes)

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
