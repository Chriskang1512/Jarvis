from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json

from jarvis.core.events import BaseEvent
from jarvis.runtime.planner.cost import RecoveryStrategy, ResumeMode
from jarvis.runtime.task.models import (
    RuntimeTask,
    StateTransitionRecord,
    TaskState,
    TransitionSource,
    now_iso,
)


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
        TaskState.RESUMING,
        TaskState.RETRYING,
        TaskState.VERIFYING,
        TaskState.PARTIAL_SUCCESS,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAIT_CONFIRM: {
        TaskState.RUNNING,
        TaskState.RESUMING,
        TaskState.PAUSED,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
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
    TaskState.RETRYING: {
        TaskState.RESUMING,
        TaskState.RUNNING,
        TaskState.PAUSED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.VERIFYING: {
        TaskState.COMPLETED,
        TaskState.SUCCESS,
        TaskState.RUNNING,
        TaskState.RETRYING,
        TaskState.PAUSED,
        TaskState.FAILED,
        TaskState.CANCELLED,
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
    transition_wall_clock_ms: int
    transition_waiting_ms: int
    transition_active_execution_ms: int
    transition_source: TransitionSource
    checkpoint_version: int
    step_input_fingerprint: str
    external_operation_id: str
    confirmation_state: str
    draft_version: int
    permission_snapshot: str
    checkpoint_created_at: str
    checkpoint_fingerprint: str

    @property
    def transition_duration_ms(self):
        """Backward-compatible checkpoint duration alias."""
        return self.transition_wall_clock_ms


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

    def transition(
        self,
        task,
        to_state,
        reason="",
        source=TransitionSource.SYSTEM,
        step_id="",
        **changes,
    ):
        to_state = normalize_state(to_state)
        source = normalize_transition_source(source)
        validate_transition(task.status, to_state)
        occurred_at = self.clock()
        wall_clock_ms = transition_wall_clock_ms(task.updated_at, occurred_at)
        record = StateTransitionRecord(
            transition_id=len(task.transition_history) + 1,
            from_state=task.status,
            to_state=to_state,
            transition_reason=str(reason or ""),
            transition_source=source,
            wall_clock_ms=wall_clock_ms,
            waiting_ms=wall_clock_ms if is_waiting_state(task.status) else 0,
            active_execution_ms=(
                wall_clock_ms if is_active_execution_state(task.status) else 0
            ),
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

    def update_snapshot(self, task, **changes):
        """Persist non-state RuntimeTask fields without bypassing checkpoints."""
        if "status" in changes:
            raise InvalidTaskTransition("DIRECT_TASK_STATE_UPDATE_FORBIDDEN")
        updated = replace(task, updated_at=self.clock(), **changes)
        self.checkpoint_store.save(create_runtime_checkpoint(updated, updated.updated_at))
        return updated

    def resume(self, task, decision, checkpoint):
        if task.status != TaskState.PAUSED:
            raise InvalidTaskTransition("Resume requires a PAUSED task.")
        validation = decision.validate_resume(checkpoint)
        resuming = self.transition(
            task,
            TaskState.RESUMING,
            reason="recovery_resume",
            source=TransitionSource.RECOVERY,
        )
        target = resume_target(validation.effective_resume_mode)
        resumed = self.transition(
            resuming,
            target,
            reason=f"resume:{validation.code}",
            source=TransitionSource.RECOVERY,
        )
        return resumed, validation

    def resume_confirmed(self, task):
        """Validate the persisted confirmation boundary before execution."""
        checkpoint = self.checkpoint_store.load(task.id)
        if checkpoint is None:
            raise InvalidTaskTransition("RUNTIME_CHECKPOINT_REQUIRED")
        if checkpoint.checkpoint_version != task.checkpoint_version:
            raise InvalidTaskTransition("RUNTIME_CHECKPOINT_VERSION_MISMATCH")
        expected = create_runtime_checkpoint(task, checkpoint.checkpoint_created_at)
        if expected.checkpoint_fingerprint != checkpoint.checkpoint_fingerprint:
            raise InvalidTaskTransition("RUNTIME_CHECKPOINT_FINGERPRINT_MISMATCH")
        if not task.step_input_fingerprint or task.permission_snapshot != "confirm_required":
            raise InvalidTaskTransition("RUNTIME_CONFIRMATION_SNAPSHOT_INVALID")
        resumed = self.transition(
            task,
            TaskState.RESUMING,
            reason="user_confirmed",
            source=TransitionSource.USER,
            confirmation_state="CONFIRMED",
        )
        return self.transition(
            resumed,
            TaskState.RUNNING,
            reason="confirmed_action_started",
            source=TransitionSource.USER,
        )

    def begin_recovery(self, task, decision, retries_completed=0):
        """Apply a policy-produced RecoveryDecision without interpreting cause."""
        strategy = decision.strategy_for(retries_completed)
        if strategy == RecoveryStrategy.BACKOFF:
            return self.transition(
                task,
                TaskState.RETRYING,
                reason="recovery_backoff",
                source=TransitionSource.RECOVERY,
            )
        if strategy in {RecoveryStrategy.WAIT, RecoveryStrategy.REAUTH}:
            return self.transition(
                task,
                TaskState.PAUSED,
                reason=f"recovery_{strategy.value.lower()}",
                source=TransitionSource.RECOVERY,
            )
        if strategy == RecoveryStrategy.FALLBACK:
            return self.transition(
                task,
                TaskState.RESUMING,
                reason="recovery_fallback",
                source=TransitionSource.RECOVERY,
            )
        return self.transition(
            task,
            TaskState.FAILED,
            reason="recovery_abort",
            source=TransitionSource.RECOVERY,
        )

    def resume_retry(self, task, decision):
        """Resume one retry after its Decision-defined wait has completed."""
        if task.status == TaskState.RETRYING:
            task = self.transition(
                task,
                TaskState.RESUMING,
                reason="retry_backoff_completed",
                source=TransitionSource.RECOVERY,
            )
        if task.status == TaskState.RESUMING:
            return self.transition(
                task,
                TaskState.RUNNING,
                reason=f"retry_resume:{decision.resume_mode.value}",
                source=TransitionSource.RECOVERY,
            )
        return task

    def publish_transition(self, task, record, checkpoint):
        if self.event_bus is None:
            return None
        event_type = task_event_type(record)
        return self.event_bus.publish(
            BaseEvent(
                event_type=event_type,
                aggregate_type="RuntimeTask",
                aggregate_id=task.id,
                revision=record.transition_id,
                idempotency_key=f"task-state:{task.id}:{record.transition_id}",
                trace_id=task.trace_id,
                correlation_id=task.correlation_id,
                payload={
                    "task_id": task.id,
                    "transition_id": record.transition_id,
                    "previous_state": record.from_state.value,
                    "new_state": record.to_state.value,
                    "transition_reason": record.transition_reason,
                    "transition_source": record.transition_source.value,
                    "wall_clock_ms": record.wall_clock_ms,
                    "waiting_ms": record.waiting_ms,
                    "active_execution_ms": record.active_execution_ms,
                    "step_id": record.step_id,
                    "checkpoint_revision": checkpoint.revision,
                    "checkpoint_fingerprint": checkpoint.checkpoint_fingerprint,
                    "trace_id": task.trace_id,
                    "correlation_id": task.correlation_id,
                },
            )
        )


def transition_task(
    task,
    to_state,
    reason="",
    source=TransitionSource.SYSTEM,
    changes=None,
):
    """Compatibility entry point used by RuntimeTask.transition()."""
    return TaskStateMachine().transition(
        task,
        to_state,
        reason=reason,
        source=source,
        **dict(changes or {}),
    )


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


def normalize_transition_source(source):
    if isinstance(source, TransitionSource):
        return source
    return TransitionSource(str(source or "").upper())


def transition_wall_clock_ms(previous_at, occurred_at):
    try:
        previous = datetime.fromisoformat(str(previous_at or ""))
        current = datetime.fromisoformat(str(occurred_at or ""))
        return max(0, int((current - previous).total_seconds() * 1000))
    except (TypeError, ValueError):
        return 0


def is_waiting_state(state):
    return state in {
        TaskState.WAIT_CONFIRM,
        TaskState.WAIT_EXTERNAL,
        TaskState.PAUSED,
    }


def is_active_execution_state(state):
    return state in {
        TaskState.RUNNING,
        TaskState.RETRYING,
        TaskState.VERIFYING,
    }


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
        "transition_wall_clock_ms": task.transition_history[-1].wall_clock_ms,
        "transition_waiting_ms": task.transition_history[-1].waiting_ms,
        "transition_active_execution_ms": (
            task.transition_history[-1].active_execution_ms
        ),
        "transition_source": task.transition_history[-1].transition_source.value,
        "checkpoint_version": task.checkpoint_version,
        "step_input_fingerprint": task.step_input_fingerprint,
        "external_operation_id": task.external_operation_id,
        "confirmation_state": task.confirmation_state,
        "draft_version": task.draft_version,
        "permission_snapshot": task.permission_snapshot,
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
        transition_wall_clock_ms=task.transition_history[-1].wall_clock_ms,
        transition_waiting_ms=task.transition_history[-1].waiting_ms,
        transition_active_execution_ms=(
            task.transition_history[-1].active_execution_ms
        ),
        transition_source=task.transition_history[-1].transition_source,
        checkpoint_version=task.checkpoint_version,
        step_input_fingerprint=task.step_input_fingerprint,
        external_operation_id=task.external_operation_id,
        confirmation_state=task.confirmation_state,
        draft_version=task.draft_version,
        permission_snapshot=task.permission_snapshot,
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
