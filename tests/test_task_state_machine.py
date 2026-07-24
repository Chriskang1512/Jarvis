import unittest

from jarvis.core.events import InMemoryEventBus
from jarvis.runtime.planner import HealthReason, HealthRecoveryPolicy, ResumeMode
from jarvis.runtime.task import (
    InMemoryTaskCheckpointStore,
    InvalidTaskTransition,
    RuntimeTask,
    TaskState,
    TaskStateMachine,
)


class TestTaskStateMachineFoundation(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.bus = InMemoryEventBus()
        self.bus.subscribe("*", self.events.append)
        self.checkpoints = InMemoryTaskCheckpointStore()
        self.machine = TaskStateMachine(
            event_bus=self.bus,
            checkpoint_store=self.checkpoints,
            clock=SequenceClock(),
        )
        self.task = RuntimeTask(id="RT-STATE", goal="state machine test")

    def test_normal_confirmation_and_verification_flow(self):
        task = self.machine.transition(self.task, TaskState.RUNNING, reason="ready")
        task = self.machine.transition(task, TaskState.WAIT_CONFIRM, reason="permission")
        task = self.machine.transition(task, TaskState.RUNNING, reason="confirmed")
        task = self.machine.transition(task, TaskState.VERIFYING, reason="steps_completed")
        task = self.machine.transition(task, TaskState.COMPLETED, reason="verified")

        self.assertEqual(task.status, TaskState.COMPLETED)
        self.assertEqual(
            [item.to_state for item in task.transition_history],
            [
                TaskState.RUNNING,
                TaskState.WAIT_CONFIRM,
                TaskState.RUNNING,
                TaskState.VERIFYING,
                TaskState.COMPLETED,
            ],
        )
        self.assertEqual(
            [event.event_type for event in self.events],
            [
                "TaskStarted",
                "TaskConfirmationRequired",
                "TaskStateChanged",
                "TaskStateChanged",
                "TaskCompleted",
            ],
        )
        self.assertEqual(
            [item.transition_id for item in task.transition_history],
            [1, 2, 3, 4, 5],
        )
        self.assertEqual(
            [item.transition_reason for item in task.transition_history],
            ["ready", "permission", "confirmed", "steps_completed", "verified"],
        )
        self.assertEqual(self.events[1].payload["transition_id"], 2)
        self.assertEqual(
            self.events[1].payload["transition_reason"],
            "permission",
        )

    def test_running_cannot_complete_without_verification(self):
        task = self.machine.transition(self.task, TaskState.RUNNING)

        with self.assertRaisesRegex(
            InvalidTaskTransition,
            "INVALID_TASK_TRANSITION:RUNNING->COMPLETED",
        ):
            self.machine.transition(task, TaskState.COMPLETED)

    def test_network_retry_flow(self):
        task = self.machine.transition(self.task, TaskState.RUNNING)
        task = self.machine.transition(task, TaskState.RETRYING, reason="NETWORK")
        task = self.machine.transition(task, TaskState.RUNNING, reason="network_restored")

        self.assertEqual(task.status, TaskState.RUNNING)
        self.assertEqual(self.events[-2].event_type, "TaskRetry")

    def test_auth_pause_resume_from_step(self):
        task = self.machine.transition(self.task, TaskState.RUNNING)
        task = self.machine.transition(task, TaskState.PAUSED, reason="AUTH_FAILURE")
        checkpoint = self.checkpoints.load(task.id)
        decision = HealthRecoveryPolicy().evaluate(HealthReason.AUTH_FAILURE)

        resumed, validation = self.machine.resume(task, decision, checkpoint)

        self.assertTrue(validation.valid)
        self.assertEqual(validation.effective_resume_mode, ResumeMode.FROM_STEP)
        self.assertEqual(resumed.status, TaskState.RUNNING)
        self.assertEqual(
            [item.to_state for item in resumed.transition_history[-2:]],
            [TaskState.RESUMING, TaskState.RUNNING],
        )

    def test_full_restart_returns_to_planning(self):
        task = self.machine.transition(self.task, TaskState.RUNNING)
        task = self.machine.transition(task, TaskState.PAUSED, reason="UNKNOWN")
        checkpoint = {
            "task_id": task.id,
            "current_step_id": "mail-send",
            "external_operation_id": "unknown",
        }
        decision = HealthRecoveryPolicy().evaluate(HealthReason.UNKNOWN).bind_checkpoint(checkpoint)

        resumed, validation = self.machine.resume(task, decision, checkpoint)

        self.assertTrue(validation.valid)
        self.assertEqual(resumed.status, TaskState.PLANNING)

    def test_checkpoint_is_saved_for_every_transition(self):
        task = self.machine.transition(self.task, TaskState.RUNNING, current_step=2)
        checkpoint = self.checkpoints.load(task.id)

        self.assertEqual(checkpoint.state, TaskState.RUNNING)
        self.assertEqual(checkpoint.current_step, 2)
        self.assertEqual(checkpoint.revision, 1)
        self.assertEqual(len(checkpoint.checkpoint_fingerprint), 64)

    def test_transition_history_does_not_store_goal_or_provider_payload(self):
        task = self.machine.transition(
            self.task,
            TaskState.RUNNING,
            reason="provider_ready",
        )
        serialized = str(task.to_dict()["transition_history"])

        self.assertNotIn(self.task.goal, serialized)
        self.assertNotIn("provider_payload", serialized)
        self.assertIn("transition_id", serialized)
        self.assertIn("transition_reason", serialized)


class SequenceClock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1
        return f"2026-07-24T14:31:{self.value:02d}"


if __name__ == "__main__":
    unittest.main()
