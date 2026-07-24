from dataclasses import dataclass, replace
import hashlib
import json

from jarvis.core.events import BaseEvent
from jarvis.runtime.planner.cost import ResumeMode
from jarvis.runtime.task.models import RuntimeTask, StateTransitionRecord, TaskState, now_iso


class InvalidTaskTransition(ValueError):
    """Raised when RuntimeTask attempts a transition outside its contract."""


ALLOWED_TRANSITIONS = {
    TaskState.PENDING: {
        TaskState.PLANNING,
        TaskState.READY,
        TaskState.RUNNING,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
    TaskState.PLANNING: {TaskState.VALIDATING, TaskState.PAUSED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.VALIDATING: {TaskState.OPTIMIZING, TaskState.READY, TaskState.PAUSED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.OPTIMIZING: {TaskState.VALIDATING, TaskState.READY, TaskState.PAUSED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.READY: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RUNNING: {
        TaskState.RUNNING,
        TaskState.WAIT_CONFIRM,
        TaskState.WAIT_EXTERNAL,
        TaskState.PAUSED,
        TaskState.RETRYING,
        TaskState.VERIFYING,
        TaskState.PARTIAL_SUCCESS,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAIT_CONFIRM: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.WAIT_EXTERNAL: {TaskState.RUNNING, TaskState.PAUSED, TaskState.RETRYING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.PAUSED: {TaskState.RESUMING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RESUMING: {
        TaskState.PLANNING,
        TaskState.READY,
        TaskState.RUNNING,
        TaskState.PAUSED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.RETRYING: {TaskState.RUNNING, TaskState.PAUSED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.VERIFYING: {
        TaskState.COMPLETED,
        TaskState.SUCCESS,
        TaskState.RETRYING,
        TaskState.PAUSED,
        TaskState.FAILED,
    },
    TaskState.PARTIAL_SUCCESS: set(),
    TaskState.COMPLETED: set(),
    TaskState.SUCCESS: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


TASK_EVENT_TYPES = {
    TaskState.RUNNING: "TaskStarted",
    TaskState.WAIT_CONFIRM: "TaskConfirmationRequired",
    TaskState.PAUSED: "TaskPaused",
    TaskState.RESUMING: "TaskResumed",
    TaskState.RETRYING: "TaskRetry",
    TaskState.COMPLETED: "TaskCompleted",
    TaskState.SUCCESS: "TaskCompleted",
    TaskState.CANCELLED: "TaskCancelled",
    TaskState.FAILED: "TaskFailed",
}


@dataclass(frozen=True)
class RuntimeTaskCheckpoint:
    """Minimal state snapshot persisted after one accepted transition."""

    task_id: str
    state: TaskState
    revision: int
    current_step: int
    completed_steps: tuple
    failed_steps: tuple
    retry_count: int
    transition_sequence: int
    checkpoint_created_at: str
    checkpoint_fingerprint: str


class InMemoryTaskCheckpointStore:
    """Foundation checkpoint store used until durable storage lands."""

    def __init__(self):
        self._items = {}

    def save(self, checkpoint):
        self._items[checkpoint.task_id] = checkpoint
        return checkpoint

    def load(self, task_id):
        return self._items.get(str(task_id or ""))


class TaskStateMachine:
    """Validate, record, publish, and checkpoint RuntimeTask transitions."""

    def __init__(self, event_bus=None, checkpoint_store=None, clock=None):
        self.event_bus = event_bus
        self.checkpoint_store = checkpoint_store or InMemoryTaskCheckpointStore()
        self.clock = clock or now_iso

    def transition(self, task, to_state, reason="", step_id="", **changes):
        to_state = normalize_state(to_state)
        validate_transition(task.status, to_state)
        occurred_at = self.clock()
        record = StateTransitionRecord(
            sequence=len(task.transition_history) + 1,
            from_state=task.status,
            to_state=to_state,
            reason=str(reason or ""),
            step_id=str(step_id or changes.get("current_step", "") or ""),
            occurred_at=occurred_at,
        )
        updated = replace(
            task,
            status=to_state,
            updated_at=occurred_at,
            transition_history=task.transition_history + (record,),
            **changes,
        )
        checkpoint = self.checkpoint_store.save(create_runtime_checkpoint(updated, occurred_at))
        self.publish_transition(updated, record, checkpoint)
        return updated

    def resume(self, task, decision, checkpoint):
        if task.status != TaskState.PAUSED:
            raise InvalidTaskTransition("Resume requires a PAUSED task.")
        validation = decision.validate_resume(checkpoint)
        resuming = self.transition(task, TaskState.RESUMING, reason="recovery_resume")
        target = resume_target(validation.effective_resume_mode)
        resumed = self.transition(
            resuming,
            target,
            reason=f"resume:{validation.code}",
        )
        return resumed, validation

    def publish_transition(self, task, record, checkpoint):
        if self.event_bus is None:
            return None
        event_type = task_event_type(record)
        return self.event_bus.publish(
            BaseEvent(
                event_type=event_type,
                aggregate_type="RuntimeTask",
                aggregate_id=task.id,
                revision=record.sequence,
                idempotency_key=f"task-state:{task.id}:{record.sequence}",
                payload={
                    "from_state": record.from_state.value,
                    "to_state": record.to_state.value,
                    "reason": record.reason,
                    "step_id": record.step_id,
                    "checkpoint_revision": checkpoint.revision,
                },
            )
        )


def transition_task(task, to_state, reason="", changes=None):
    """Compatibility entry point used by RuntimeTask.transition()."""
    return TaskStateMachine().transition(task, to_state, reason=reason, **dict(changes or {}))


def validate_transition(from_state, to_state):
    from_state = normalize_state(from_state)
    to_state = normalize_state(to_state)
    if to_state not in ALLOWED_TRANSITIONS.get(from_state, set()):
        raise InvalidTaskTransition(
            f"INVALID_TASK_TRANSITION:{from_state.value}->{to_state.value}"
        )


def normalize_state(state):
    if isinstance(state, TaskState):
        return state
    return TaskState(str(state or ""))


def create_runtime_checkpoint(task, occurred_at=None):
    created_at = occurred_at or now_iso()
    payload = {
        "task_id": task.id,
        "state": task.status.value,
        "current_step": task.current_step,
        "completed_steps": list(task.completed_steps),
        "failed_steps": list(task.failed_steps),
        "retry_count": task.retry_count,
        "transition_sequence": len(task.transition_history),
        "step_records": [
            {
                "step_index": record.step_index,
                "status": record.status.value,
                "attempts": record.attempts,
                "failure_reason": record.failure_reason,
            }
            for record in task.step_records
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return RuntimeTaskCheckpoint(
        task_id=task.id,
        state=task.status,
        revision=len(task.transition_history),
        current_step=task.current_step,
        completed_steps=tuple(task.completed_steps),
        failed_steps=tuple(task.failed_steps),
        retry_count=task.retry_count,
        transition_sequence=len(task.transition_history),
        checkpoint_created_at=created_at,
        checkpoint_fingerprint=fingerprint,
    )


def resume_target(resume_mode):
    if resume_mode == ResumeMode.FROM_STEP:
        return TaskState.RUNNING
    if resume_mode == ResumeMode.FROM_CHECKPOINT:
        return TaskState.RUNNING
    return TaskState.PLANNING


def task_event_type(record):
    if record.to_state == TaskState.RUNNING and record.from_state not in {
        TaskState.PENDING,
        TaskState.READY,
    }:
        return "TaskStateChanged"
    return TASK_EVENT_TYPES.get(record.to_state, "TaskStateChanged")
