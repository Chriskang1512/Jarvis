import threading
import time
import unittest

from jarvis.runtime import (
    BusyPolicy,
    RuntimeBusyError,
    RuntimeTurnLock,
    TurnOwner,
    TurnPriority,
)


class TestRuntimeTurnLock(unittest.TestCase):
    def test_priority_enum_has_stable_operational_order(self):
        self.assertGreater(TurnPriority.SYSTEM, TurnPriority.EMERGENCY)
        self.assertGreater(TurnPriority.EMERGENCY, TurnPriority.USER)
        self.assertGreater(TurnPriority.USER, TurnPriority.SCHEDULE)
        self.assertGreater(TurnPriority.SCHEDULE, TurnPriority.PLUGIN)
        self.assertGreater(TurnPriority.PLUGIN, TurnPriority.BACKGROUND)

    def test_reject_reports_current_owner(self):
        lock = RuntimeTurnLock()
        dashboard = lock.acquire(TurnOwner.DASHBOARD)

        with self.assertRaises(RuntimeBusyError) as raised:
            lock.acquire(TurnOwner.VOICE, BusyPolicy.REJECT)

        self.assertEqual(raised.exception.current_owner, TurnOwner.DASHBOARD)
        self.assertEqual(lock.owner, TurnOwner.DASHBOARD)
        self.assertTrue(lock.release(dashboard))

    def test_wrong_token_cannot_unlock_runtime(self):
        first = RuntimeTurnLock()
        second = RuntimeTurnLock()
        dashboard = first.acquire(TurnOwner.DASHBOARD)
        foreign = second.acquire(TurnOwner.API)

        self.assertFalse(first.release(foreign))
        self.assertEqual(first.owner, TurnOwner.DASHBOARD)
        self.assertTrue(first.release(dashboard))
        self.assertTrue(second.release(foreign))

    def test_wait_policy_acquires_after_owner_releases(self):
        lock = RuntimeTurnLock()
        dashboard = lock.acquire(TurnOwner.DASHBOARD)
        acquired = []

        def wait_for_voice():
            acquired.append(lock.acquire(TurnOwner.VOICE, BusyPolicy.WAIT, timeout=1))

        waiter = threading.Thread(target=wait_for_voice)
        waiter.start()
        self.assertEqual(lock.owner, TurnOwner.DASHBOARD)
        self.assertTrue(lock.release(dashboard))
        waiter.join(timeout=1)

        self.assertEqual(acquired[0].owner, TurnOwner.VOICE)
        self.assertTrue(lock.release(acquired[0]))

    def test_callbacks_follow_token_lifecycle(self):
        events = []
        lock = RuntimeTurnLock(
            on_acquired=lambda token: events.append(("acquired", token.owner)),
            on_released=lambda token, reason: events.append(("released", reason)),
        )

        token = lock.acquire(TurnOwner.PLUGIN)
        lock.release(token, "done")

        self.assertEqual(
            events,
            [("acquired", TurnOwner.PLUGIN), ("released", "done")],
        )

    def test_turn_carries_runtime_metadata(self):
        lock = RuntimeTurnLock()
        turn = lock.acquire(
            TurnOwner.VOICE,
            turn_timeout=30,
            priority=100,
            source="microphone",
            conversation_id="VOICE-1",
        )

        snapshot = turn.snapshot()

        self.assertEqual(snapshot["owner"], "voice")
        self.assertEqual(snapshot["state"], "running")
        self.assertEqual(snapshot["timeout"], 30)
        self.assertEqual(snapshot["priority"], 100)
        self.assertEqual(snapshot["source"], "microphone")
        self.assertEqual(snapshot["conversation_id"], "VOICE-1")
        self.assertTrue(snapshot["turn_id"].startswith("TURN-"))
        self.assertTrue(snapshot["lock_token"].startswith("LOCK-"))
        self.assertNotEqual(snapshot["turn_id"], snapshot["lock_token"])
        lock.release(turn)

    def test_task_and_turn_lifecycles_are_linked_but_separate(self):
        lock = RuntimeTurnLock()
        turn = lock.acquire(TurnOwner.VOICE)

        self.assertTrue(lock.link_task(turn, "RT-42", "STEP-3"))

        self.assertEqual(turn.task_id, "RT-42")
        self.assertEqual(turn.step_id, "STEP-3")
        self.assertEqual(turn.state.value, "running")
        lock.release(turn)

    def test_higher_priority_preempt_requests_cancel_then_acquires(self):
        lock = RuntimeTurnLock()
        voice = lock.acquire(TurnOwner.VOICE, priority=100)
        emergency_turns = []

        def acquire_emergency():
            emergency_turns.append(
                lock.acquire(
                    TurnOwner.EMERGENCY,
                    BusyPolicy.PREEMPT,
                    timeout=1,
                    priority=1000,
                    source="emergency_phrase",
                )
            )

        preemptor = threading.Thread(target=acquire_emergency)
        preemptor.start()
        for _ in range(100):
            if voice.cancellation_requested:
                break
            time.sleep(0.005)

        self.assertTrue(voice.cancellation_requested)
        self.assertEqual(voice.state.value, "interrupting")
        lock.release(voice, reason="preempted")
        preemptor.join(timeout=1)

        self.assertEqual(emergency_turns[0].owner, TurnOwner.EMERGENCY)
        self.assertEqual(voice.state.value, "interrupted")
        lock.release(emergency_turns[0])

    def test_lower_priority_preempt_is_rejected(self):
        lock = RuntimeTurnLock()
        voice = lock.acquire(TurnOwner.VOICE, priority=100)

        with self.assertRaises(RuntimeBusyError):
            lock.acquire(
                TurnOwner.PLUGIN,
                BusyPolicy.PREEMPT,
                priority=10,
            )

        self.assertFalse(voice.cancellation_requested)
        lock.release(voice)

    def test_queue_runs_preempt_then_priority_then_fifo(self):
        lock = RuntimeTurnLock()
        running = lock.acquire(TurnOwner.VOICE, priority=TurnPriority.USER)
        acquired = []
        release_events = {
            "emergency": threading.Event(),
            "plugin": threading.Event(),
            "scheduler": threading.Event(),
        }

        def wait_for(owner, policy, priority, name):
            turn = lock.acquire(owner, policy, timeout=2, priority=priority)
            acquired.append(name)
            release_events[name].wait(timeout=1)
            lock.release(turn)

        workers = [
            threading.Thread(
                target=wait_for,
                args=(TurnOwner.PLUGIN, BusyPolicy.QUEUE, TurnPriority.PLUGIN, "plugin"),
            ),
            threading.Thread(
                target=wait_for,
                args=(
                    TurnOwner.SCHEDULER,
                    BusyPolicy.QUEUE,
                    TurnPriority.SCHEDULE,
                    "scheduler",
                ),
            ),
            threading.Thread(
                target=wait_for,
                args=(
                    TurnOwner.EMERGENCY,
                    BusyPolicy.PREEMPT,
                    TurnPriority.EMERGENCY,
                    "emergency",
                ),
            ),
        ]
        for worker in workers:
            worker.start()
        for _ in range(100):
            if lock.queued == 3:
                break
            time.sleep(0.005)

        self.assertEqual(
            [item["owner"] for item in lock.snapshot()["queue"]],
            ["emergency", "scheduler", "plugin"],
        )
        lock.release(running, reason="preempted")
        for name in ("emergency", "scheduler", "plugin"):
            for _ in range(100):
                if name in acquired:
                    break
                time.sleep(0.005)
            release_events[name].set()
        for worker in workers:
            worker.join(timeout=1)

        self.assertEqual(acquired, ["emergency", "scheduler", "plugin"])

    def test_soft_and_hard_timeout_request_cooperative_cancellation(self):
        lock = RuntimeTurnLock()
        turn = lock.acquire(
            TurnOwner.PLUGIN,
            soft_timeout=0.02,
            hard_timeout=0.05,
        )

        time.sleep(0.08)

        self.assertTrue(turn.cancellation_requested)
        self.assertEqual(turn.state.value, "interrupting")
        lock.release(turn, reason="hard_timeout")
        self.assertEqual(turn.state.value, "interrupted")

    def test_soft_timeout_must_precede_hard_timeout(self):
        with self.assertRaisesRegex(ValueError, "Soft timeout"):
            RuntimeTurnLock().acquire(
                TurnOwner.API,
                soft_timeout=10,
                hard_timeout=5,
            )

    def test_timeout_stage_gets_an_independent_budget(self):
        lock = RuntimeTurnLock()
        turn = lock.acquire(
            TurnOwner.VOICE,
            soft_timeout=0.02,
            hard_timeout=0.04,
        )

        time.sleep(0.015)
        changed = lock.set_timeout_stage(
            turn,
            "TTS_PLAYBACK",
            soft_timeout=0.04,
            hard_timeout=0.08,
        )
        time.sleep(0.03)

        self.assertTrue(changed)
        self.assertEqual(turn.timeout_stage, "TTS_PLAYBACK")
        self.assertFalse(turn.cancellation_requested)
        lock.release(turn)

    def test_idle_timeout_stage_can_pause_timers(self):
        lock = RuntimeTurnLock()
        turn = lock.acquire(
            TurnOwner.VOICE,
            soft_timeout=0.01,
            hard_timeout=0.02,
        )

        lock.set_timeout_stage(
            turn,
            "FOLLOW_UP_WAIT",
            soft_timeout=None,
            hard_timeout=None,
        )
        time.sleep(0.03)

        self.assertIsNone(turn.soft_timeout)
        self.assertIsNone(turn.hard_timeout)
        self.assertFalse(turn.cancellation_requested)
        lock.release(turn)


if __name__ == "__main__":
    unittest.main()
