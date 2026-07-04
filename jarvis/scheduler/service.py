from typing import Protocol, runtime_checkable
from uuid import uuid4

from jarvis.scheduler.clock import SystemClock
from jarvis.scheduler.exceptions import SchedulerTaskNotFound
from jarvis.scheduler.models import Schedule, ScheduledTask, TaskState, TriggerResult
from jarvis.scheduler.storage import InMemoryTaskStore


@runtime_checkable
class Scheduler(Protocol):
    """Scheduler Foundation interface."""

    def schedule(self, request) -> ScheduledTask:
        """Create and store a scheduled task."""
        ...

    def get(self, task_id: str) -> ScheduledTask | None:
        """Return one task by ID or None."""
        ...

    def list(self) -> list[ScheduledTask]:
        """Return all tasks."""
        ...

    def cancel(self, task_id: str) -> ScheduledTask:
        """Cancel one task."""
        ...

    def due_tasks(self, now) -> list[ScheduledTask]:
        """Return tasks due at the given time."""
        ...

    def trigger_due(self, now=None, execution_runner=None) -> list[TriggerResult]:
        """Manually trigger due tasks."""
        ...


class InMemoryScheduler:
    """Scheduler Foundation implementation backed by an in-memory store."""

    def __init__(self, store=None, clock=None, execution_runner=None, id_factory=None):
        """Create an in-memory scheduler with injectable dependencies."""
        self.store = store or InMemoryTaskStore()
        self.clock = clock or SystemClock()
        self.execution_runner = execution_runner
        self.id_factory = id_factory or create_task_id

    def schedule(self, request):
        """Create and store a scheduled task from a request."""
        now = self.clock.now()
        task_id = request.task_id or self.id_factory()
        task = ScheduledTask(
            task_id=task_id,
            schedule=Schedule(run_at=request.run_at),
            payload=request.payload,
            state=TaskState.PENDING,
            created_at=now,
            updated_at=now,
            metadata=dict(request.metadata),
        )
        return self.store.save(task)

    def get(self, task_id):
        """Return one task by ID or None."""
        return self.store.get(task_id)

    def list(self):
        """Return all scheduled tasks."""
        return self.store.list()

    def cancel(self, task_id):
        """Cancel one scheduled task."""
        task = self.get(task_id)

        if task is None:
            raise SchedulerTaskNotFound(f"Scheduled task not found: {task_id}")

        return self.store.save(task.transition(TaskState.CANCELLED, self.clock.now()))

    def due_tasks(self, now):
        """Return tasks that are due at the given time."""
        return [task for task in self.list() if task.is_due(now)]

    def trigger_due(self, now=None, execution_runner=None):
        """Manually trigger due tasks and return per-task trigger results."""
        trigger_time = now or self.clock.now()
        runner = execution_runner or self.execution_runner

        if runner is None:
            raise ValueError("Execution runner is required to trigger scheduled tasks.")

        trigger_results = []

        for task in self.due_tasks(trigger_time):
            running_task = self.store.save(task.transition(TaskState.RUNNING, self.clock.now()))

            try:
                unified_result = runner.run_unified(running_task.payload)
            except Exception as error:
                failed_task = self.store.save(
                    running_task.transition(
                        TaskState.FAILED,
                        self.clock.now(),
                        error=str(error),
                    )
                )
                trigger_results.append(TriggerResult(task=failed_task, error=str(error)))
                continue

            completed_task = self.store.save(
                running_task.transition(
                    TaskState.COMPLETED,
                    self.clock.now(),
                    result=unified_result,
                )
            )
            trigger_results.append(TriggerResult(task=completed_task, result=unified_result))

        return trigger_results


SchedulerService = InMemoryScheduler


def create_task_id():
    """Create a diagnostic-friendly scheduled task ID."""
    return f"task_{uuid4().hex[:12]}"
