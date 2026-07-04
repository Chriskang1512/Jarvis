from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum


class TaskState(Enum):
    """Lifecycle states for scheduled tasks."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ScheduleRequest:
    """Input DTO for creating a scheduled task."""

    run_at: datetime
    payload: object
    metadata: dict = field(default_factory=dict)
    task_id: str = ""


@dataclass(frozen=True)
class Schedule:
    """Time rule for a scheduled task.

    Beta.6 supports one-shot schedules only.
    """

    run_at: datetime
    type: str = "one-shot"

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "run_at": self.run_at.isoformat(),
            "type": self.type,
        }


@dataclass(frozen=True)
class ScheduledTask:
    """Stored scheduled task with lifecycle state."""

    task_id: str
    schedule: Schedule
    payload: object
    state: TaskState
    created_at: datetime
    updated_at: datetime
    metadata: dict = field(default_factory=dict)
    result: object = None
    error: str = ""

    def is_due(self, now):
        """Return whether this task should be triggered at the given time."""
        return self.state in {TaskState.PENDING, TaskState.READY} and self.schedule.run_at <= now

    def transition(self, state, updated_at, result=None, error=""):
        """Return a copy with updated lifecycle state."""
        return replace(
            self,
            state=state,
            updated_at=updated_at,
            result=result,
            error=error,
        )

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "task_id": self.task_id,
            "schedule": self.schedule.to_dict(),
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": dict(self.metadata),
            "result": self.result.to_dict() if hasattr(self.result, "to_dict") else self.result,
            "error": self.error,
        }


@dataclass(frozen=True)
class TriggerResult:
    """Result for one manually triggered scheduled task."""

    task: ScheduledTask
    result: object = None
    error: str = ""

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "task": self.task.to_dict(),
            "result": self.result.to_dict() if hasattr(self.result, "to_dict") else self.result,
            "error": self.error,
        }
