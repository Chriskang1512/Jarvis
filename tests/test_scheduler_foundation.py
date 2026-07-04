from datetime import datetime, timedelta
import inspect
import unittest

from jarvis.result_merge import UnifiedResult
from jarvis.scheduler import (
    FixedClock,
    InMemoryScheduler,
    InMemoryTaskStore,
    Schedule,
    ScheduledTask,
    Scheduler,
    SchedulerTaskNotFound,
    ScheduleRequest,
    TaskState,
)
from jarvis.scheduler import service as scheduler_service_module


class TestSchedulerFoundation(unittest.TestCase):
    """Test v0.4 Beta.6 Scheduler Foundation."""

    def test_schedule_request_creates_scheduled_task(self):
        """Check ScheduleRequest -> Schedule -> ScheduledTask creation."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        run_at = now + timedelta(minutes=10)
        scheduler = create_scheduler(now)

        task = scheduler.schedule(
            ScheduleRequest(
                run_at=run_at,
                payload={"plan_id": "plan_test"},
                metadata={"source": "test"},
                task_id="task_test",
            )
        )

        self.assertEqual(task.task_id, "task_test")
        self.assertIsInstance(task.schedule, Schedule)
        self.assertEqual(task.schedule.run_at, run_at)
        self.assertEqual(task.schedule.type, "one-shot")
        self.assertEqual(task.payload, {"plan_id": "plan_test"})
        self.assertEqual(task.state, TaskState.PENDING)
        self.assertEqual(task.created_at, now)
        self.assertEqual(task.updated_at, now)
        self.assertEqual(task.metadata["source"], "test")

    def test_schedule_model_preserves_run_at(self):
        """Check Schedule stores one-shot run_at values."""
        run_at = datetime(2026, 7, 4, 9, 0, 0)

        schedule = Schedule(run_at=run_at)

        self.assertEqual(schedule.run_at, run_at)
        self.assertEqual(schedule.to_dict()["run_at"], "2026-07-04T09:00:00")

    def test_task_state_enum_values(self):
        """Check TaskState exposes stable lifecycle values."""
        self.assertEqual(TaskState.PENDING.value, "PENDING")
        self.assertEqual(TaskState.READY.value, "READY")
        self.assertEqual(TaskState.RUNNING.value, "RUNNING")
        self.assertEqual(TaskState.COMPLETED.value, "COMPLETED")
        self.assertEqual(TaskState.FAILED.value, "FAILED")
        self.assertEqual(TaskState.CANCELLED.value, "CANCELLED")

    def test_is_due_when_run_at_is_before_or_equal_now(self):
        """Check PENDING and READY tasks are due when run_at <= now."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        past_task = create_task(run_at=now - timedelta(seconds=1), state=TaskState.PENDING)
        equal_task = create_task(run_at=now, state=TaskState.READY)

        self.assertTrue(past_task.is_due(now))
        self.assertTrue(equal_task.is_due(now))

    def test_is_not_due_when_run_at_is_future(self):
        """Check future tasks are not due."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        task = create_task(run_at=now + timedelta(seconds=1), state=TaskState.PENDING)

        self.assertFalse(task.is_due(now))

    def test_non_pending_states_are_excluded_from_due(self):
        """Check cancelled, running, completed, and failed tasks are never due."""
        now = datetime(2026, 7, 4, 9, 0, 0)

        for state in [TaskState.CANCELLED, TaskState.RUNNING, TaskState.COMPLETED, TaskState.FAILED]:
            task = create_task(run_at=now - timedelta(minutes=1), state=state)
            self.assertFalse(task.is_due(now))

    def test_scheduler_schedule_get_list_and_cancel(self):
        """Check Scheduler schedule, get, list, and cancel operations."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = create_scheduler(now)
        task = scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "plan_test"}))

        self.assertEqual(scheduler.get(task.task_id), task)
        self.assertEqual(scheduler.list(), [task])

        cancelled = scheduler.cancel(task.task_id)

        self.assertEqual(cancelled.state, TaskState.CANCELLED)
        self.assertEqual(scheduler.get(task.task_id).state, TaskState.CANCELLED)
        self.assertEqual(scheduler.due_tasks(now), [])

    def test_cancel_unknown_task_raises(self):
        """Check cancelling an unknown task is explicit."""
        scheduler = create_scheduler(datetime(2026, 7, 4, 9, 0, 0))

        with self.assertRaises(SchedulerTaskNotFound):
            scheduler.cancel("missing")

    def test_due_tasks_returns_only_due_tasks(self):
        """Check due_tasks filters by state and run_at."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = create_scheduler(now)
        due = scheduler.schedule(ScheduleRequest(run_at=now, payload="due", task_id="due"))
        scheduler.schedule(ScheduleRequest(run_at=now + timedelta(minutes=1), payload="future", task_id="future"))
        cancelled = scheduler.schedule(ScheduleRequest(run_at=now, payload="cancelled", task_id="cancelled"))
        scheduler.cancel(cancelled.task_id)

        self.assertEqual(scheduler.due_tasks(now), [due])

    def test_trigger_due_calls_execution_runner_run_unified(self):
        """Check trigger_due manually executes due tasks through run_unified."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        runner = RecordingExecutionRunner()
        scheduler = create_scheduler(now, execution_runner=runner)
        scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "plan_due"}, task_id="task_due"))

        results = scheduler.trigger_due(now)

        self.assertEqual(runner.seen_payloads, [{"plan_id": "plan_due"}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].task.state, TaskState.COMPLETED)
        self.assertEqual(results[0].result.summary, "ran plan_due")
        self.assertEqual(scheduler.get("task_due").state, TaskState.COMPLETED)

    def test_trigger_due_marks_failed_task_failed(self):
        """Check task failures are recorded as FAILED."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = create_scheduler(now, execution_runner=PartiallyFailingExecutionRunner())
        scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "fail"}, task_id="task_fail"))

        results = scheduler.trigger_due(now)

        self.assertEqual(results[0].task.state, TaskState.FAILED)
        self.assertEqual(results[0].error, "runner failed")
        self.assertEqual(scheduler.get("task_fail").state, TaskState.FAILED)

    def test_trigger_due_continues_after_one_task_fails(self):
        """Check one failed task does not stop other due tasks."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = create_scheduler(now, execution_runner=PartiallyFailingExecutionRunner())
        scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "fail"}, task_id="task_fail"))
        scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "success"}, task_id="task_success"))

        results = scheduler.trigger_due(now)

        self.assertEqual([result.task.state for result in results], [TaskState.FAILED, TaskState.COMPLETED])
        self.assertEqual(scheduler.get("task_fail").state, TaskState.FAILED)
        self.assertEqual(scheduler.get("task_success").state, TaskState.COMPLETED)

    def test_in_memory_task_store_instances_are_isolated(self):
        """Check InMemoryTaskStore does not share state across instances."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        first = InMemoryTaskStore()
        second = InMemoryTaskStore()
        task = create_task(task_id="task_one", run_at=now, state=TaskState.PENDING)

        first.save(task)

        self.assertEqual(first.list(), [task])
        self.assertEqual(second.list(), [])

    def test_fixed_clock_makes_schedule_creation_deterministic(self):
        """Check FixedClock controls created_at and updated_at."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = create_scheduler(now)

        task = scheduler.schedule(ScheduleRequest(run_at=now, payload="payload"))

        self.assertEqual(task.created_at, now)
        self.assertEqual(task.updated_at, now)

    def test_scheduler_interface_accepts_in_memory_scheduler(self):
        """Check InMemoryScheduler satisfies the Scheduler protocol."""
        self.assertTrue(isinstance(create_scheduler(datetime(2026, 7, 4, 9, 0, 0)), Scheduler))

    def test_scheduler_does_not_import_forbidden_layers(self):
        """Check Scheduler does not know Planner, Voice, or Capabilities."""
        source = inspect.getsource(scheduler_service_module)
        forbidden = [
            "jarvis.planner",
            "jarvis.voice",
            "jarvis.capabilities",
            "IntentPlanner",
            "VoiceService",
            "Capability",
        ]

        for value in forbidden:
            self.assertNotIn(value, source)


def create_scheduler(now, execution_runner=None):
    """Create a deterministic in-memory scheduler."""
    return InMemoryScheduler(
        clock=FixedClock(now),
        execution_runner=execution_runner,
        id_factory=DeterministicIdFactory(),
    )


def create_task(task_id="task_test", run_at=None, state=TaskState.PENDING):
    """Create a scheduled task for model tests."""
    now = datetime(2026, 7, 4, 9, 0, 0)
    return ScheduledTask(
        task_id=task_id,
        schedule=Schedule(run_at=run_at or now),
        payload={"plan_id": "plan_test"},
        state=state,
        created_at=now,
        updated_at=now,
        metadata={},
    )


class DeterministicIdFactory:
    """Simple deterministic task ID factory."""

    def __init__(self):
        """Create an ID factory."""
        self.count = 0

    def __call__(self):
        """Return the next deterministic ID."""
        self.count += 1
        return f"task_{self.count:03d}"


class RecordingExecutionRunner:
    """Execution runner stub that records payloads."""

    def __init__(self):
        """Create an empty recording runner."""
        self.seen_payloads = []

    def run_unified(self, payload):
        """Record payload and return a UnifiedResult."""
        self.seen_payloads.append(payload)
        return UnifiedResult(summary=f"ran {payload['plan_id']}")


class PartiallyFailingExecutionRunner:
    """Execution runner stub that fails selected payloads."""

    def run_unified(self, payload):
        """Raise for fail payloads and return a UnifiedResult otherwise."""
        if payload["plan_id"] == "fail":
            raise RuntimeError("runner failed")

        return UnifiedResult(summary=f"ran {payload['plan_id']}")


if __name__ == "__main__":
    unittest.main()
