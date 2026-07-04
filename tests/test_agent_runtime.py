from datetime import datetime, timedelta
import inspect
import unittest

from jarvis.agent_runtime import AgentRuntime, AgentRuntimeState, AgentRuntimeStopped, ExecutionKernel
from jarvis.agent_runtime import service as agent_runtime_service_module
from jarvis.result_merge import UnifiedResult
from jarvis.scheduler import FixedClock, InMemoryScheduler, ScheduleRequest, TaskState


class TestAgentRuntime(unittest.TestCase):
    """Test v0.4 Beta.7 Agent Runtime."""

    def test_runtime_starts_and_stops_without_background_loop(self):
        """Check runtime lifecycle is explicit and manual."""
        runtime = create_runtime()

        self.assertEqual(runtime.state, AgentRuntimeState.STOPPED)
        self.assertEqual(runtime.start(), AgentRuntimeState.IDLE)
        self.assertEqual(runtime.stop(), AgentRuntimeState.STOPPED)

    def test_tick_requires_started_runtime(self):
        """Check stopped runtime cannot tick."""
        runtime = create_runtime()

        with self.assertRaises(AgentRuntimeStopped):
            runtime.tick()

    def test_tick_checks_scheduler_due_tasks(self):
        """Check AgentRuntime asks Scheduler for due tasks."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = RecordingScheduler(clock=FixedClock(now))
        runtime = AgentRuntime(scheduler=scheduler, execution_kernel=RecordingKernel(), clock=FixedClock(now))
        runtime.start()

        result = runtime.tick(now)

        self.assertEqual(scheduler.seen_due_times, [now])
        self.assertEqual(result.due_count, 0)
        self.assertEqual(result.runtime_state, AgentRuntimeState.IDLE)
        self.assertEqual(runtime.state, AgentRuntimeState.IDLE)

    def test_tick_triggers_due_tasks_through_scheduler_and_kernel(self):
        """Check Runtime coordinates Scheduler and Execution Kernel."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        kernel = RecordingKernel()
        scheduler = InMemoryScheduler(clock=FixedClock(now))
        scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "plan_due"}, task_id="task_due"))
        runtime = AgentRuntime(scheduler=scheduler, execution_kernel=kernel, clock=FixedClock(now))
        runtime.start()

        result = runtime.tick(now)

        self.assertEqual(kernel.seen_payloads, [{"plan_id": "plan_due"}])
        self.assertEqual(result.due_count, 1)
        self.assertEqual(len(result.trigger_results), 1)
        self.assertEqual(result.trigger_results[0].task.state, TaskState.COMPLETED)
        self.assertEqual(result.trigger_results[0].result.summary, "ran plan_due")
        self.assertEqual(scheduler.get("task_due").state, TaskState.COMPLETED)
        self.assertEqual(runtime.state, AgentRuntimeState.IDLE)

    def test_tick_ignores_future_tasks(self):
        """Check future tasks are not triggered."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        kernel = RecordingKernel()
        scheduler = InMemoryScheduler(clock=FixedClock(now))
        scheduler.schedule(
            ScheduleRequest(
                run_at=now + timedelta(minutes=1),
                payload={"plan_id": "future"},
                task_id="task_future",
            )
        )
        runtime = AgentRuntime(scheduler=scheduler, execution_kernel=kernel, clock=FixedClock(now))
        runtime.start()

        result = runtime.tick(now)

        self.assertEqual(result.due_count, 0)
        self.assertEqual(kernel.seen_payloads, [])
        self.assertEqual(scheduler.get("task_future").state, TaskState.PENDING)

    def test_task_failure_does_not_fail_runtime_when_scheduler_isolates_it(self):
        """Check task-level failure remains task-level."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = InMemoryScheduler(clock=FixedClock(now))
        scheduler.schedule(ScheduleRequest(run_at=now, payload={"plan_id": "fail"}, task_id="task_fail"))
        runtime = AgentRuntime(scheduler=scheduler, execution_kernel=FailingKernel(), clock=FixedClock(now))
        runtime.start()

        result = runtime.tick(now)

        self.assertEqual(runtime.state, AgentRuntimeState.IDLE)
        self.assertEqual(result.runtime_state, AgentRuntimeState.IDLE)
        self.assertEqual(result.trigger_results[0].task.state, TaskState.FAILED)
        self.assertEqual(result.trigger_results[0].error, "kernel failed")

    def test_runtime_failure_state_when_scheduler_trigger_raises(self):
        """Check runtime records failure if scheduler trigger itself fails."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        scheduler = BrokenScheduler()
        runtime = AgentRuntime(scheduler=scheduler, execution_kernel=RecordingKernel(), clock=FixedClock(now))
        runtime.start()

        result = runtime.tick(now)

        self.assertEqual(runtime.state, AgentRuntimeState.FAILED)
        self.assertEqual(result.runtime_state, AgentRuntimeState.FAILED)
        self.assertEqual(result.error, "scheduler failed")

    def test_runtime_uses_fixed_clock_when_now_is_not_supplied(self):
        """Check runtime clock makes ticks deterministic."""
        now = datetime(2026, 7, 4, 9, 0, 0)
        runtime = create_runtime(now=now)
        runtime.start()

        result = runtime.tick()

        self.assertEqual(result.checked_at, now)

    def test_execution_kernel_protocol_accepts_recording_kernel(self):
        """Check kernel is defined by run_unified only."""
        self.assertTrue(isinstance(RecordingKernel(), ExecutionKernel))

    def test_agent_runtime_does_not_import_planner_voice_or_capabilities(self):
        """Check AgentRuntime stays above Scheduler and Kernel only."""
        source = inspect.getsource(agent_runtime_service_module)
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


def create_runtime(now=None):
    """Create a runtime with deterministic dependencies."""
    fixed_now = now or datetime(2026, 7, 4, 9, 0, 0)
    return AgentRuntime(
        scheduler=InMemoryScheduler(clock=FixedClock(fixed_now)),
        execution_kernel=RecordingKernel(),
        clock=FixedClock(fixed_now),
    )


class RecordingKernel:
    """Execution kernel stub that records payloads."""

    def __init__(self):
        """Create an empty recording kernel."""
        self.seen_payloads = []

    def run_unified(self, payload):
        """Record payload and return a UnifiedResult."""
        self.seen_payloads.append(payload)
        return UnifiedResult(summary=f"ran {payload['plan_id']}")


class FailingKernel:
    """Execution kernel stub that always fails."""

    def run_unified(self, payload):
        """Raise a deterministic error."""
        raise RuntimeError("kernel failed")


class RecordingScheduler(InMemoryScheduler):
    """Scheduler stub that records due checks."""

    def __init__(self, clock):
        """Create a recording scheduler."""
        super().__init__(clock=clock)
        self.seen_due_times = []

    def due_tasks(self, now):
        """Record due check times."""
        self.seen_due_times.append(now)
        return super().due_tasks(now)


class BrokenScheduler:
    """Scheduler stub whose trigger fails outside task isolation."""

    def due_tasks(self, now):
        """Return a fake due task count."""
        return [object()]

    def trigger_due(self, now, execution_runner=None):
        """Raise a scheduler-level failure."""
        raise RuntimeError("scheduler failed")


if __name__ == "__main__":
    unittest.main()
