"""Runtime turns, priority queueing, timeouts, and cooperative preemption."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from itertools import count
from threading import Condition, Event, RLock, Timer
from time import monotonic
from uuid import uuid4

from jarvis.debug_trace import trace_event


class TurnOwner(str, Enum):
    VOICE = "voice"
    DASHBOARD = "dashboard"
    TOUCH_PORTAL = "touch_portal"
    MOBILE = "mobile"
    API = "api"
    PLUGIN = "plugin"
    SCHEDULER = "scheduler"
    EMERGENCY = "emergency"
    SYSTEM = "system"


class TurnPriority(IntEnum):
    BACKGROUND = 100
    PLUGIN = 200
    SCHEDULE = 300
    USER = 500
    EMERGENCY = 900
    SYSTEM = 1000


DEFAULT_PRIORITY = {
    TurnOwner.VOICE: TurnPriority.USER,
    TurnOwner.DASHBOARD: TurnPriority.USER,
    TurnOwner.TOUCH_PORTAL: TurnPriority.USER,
    TurnOwner.MOBILE: TurnPriority.USER,
    TurnOwner.API: TurnPriority.USER,
    TurnOwner.PLUGIN: TurnPriority.PLUGIN,
    TurnOwner.SCHEDULER: TurnPriority.SCHEDULE,
    TurnOwner.EMERGENCY: TurnPriority.EMERGENCY,
    TurnOwner.SYSTEM: TurnPriority.SYSTEM,
}


class TurnState(str, Enum):
    RUNNING = "running"
    INTERRUPTING = "interrupting"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class BusyPolicy(str, Enum):
    REJECT = "reject"
    WAIT = "wait"
    QUEUE = "queue"
    PREEMPT = "preempt"


@dataclass
class RuntimeTurn:
    owner: TurnOwner
    state: TurnState = TurnState.RUNNING
    started_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="milliseconds")
    )
    soft_timeout: float | None = None
    hard_timeout: float | None = None
    priority: int = int(TurnPriority.BACKGROUND)
    priority_name: str = TurnPriority.BACKGROUND.name
    source: str = ""
    conversation_id: str = ""
    task_id: str = ""
    step_id: str = ""
    language_context: object | None = None
    timeout_stage: str = "PROCESSING"
    timeout_stage_started_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="milliseconds")
    )
    turn_id: str = ""
    lock_token: str = field(default_factory=lambda: f"LOCK-{uuid4().hex.upper()}")
    _started_monotonic: float = field(default_factory=monotonic, repr=False)
    _cancel_event: Event = field(default_factory=Event, repr=False)
    _soft_timer: Timer | None = field(default=None, repr=False)
    _hard_timer: Timer | None = field(default=None, repr=False)

    @property
    def token(self):
        return self.lock_token

    @property
    def token_id(self):
        return self.lock_token

    @property
    def acquired_at(self):
        return self._started_monotonic

    @property
    def timeout(self):
        return self.hard_timeout

    @property
    def cancellation_requested(self):
        return self._cancel_event.is_set()

    def request_cancellation(self):
        self.state = TurnState.INTERRUPTING
        self._cancel_event.set()

    def snapshot(self):
        return {
            "owner": self.owner.value,
            "state": self.state.value,
            "started_at": self.started_at,
            "soft_timeout": self.soft_timeout,
            "hard_timeout": self.hard_timeout,
            "timeout": self.hard_timeout,
            "priority": self.priority,
            "priority_name": self.priority_name,
            "source": self.source,
            "conversation_id": self.conversation_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "language_context": (
                self.language_context.to_dict()
                if hasattr(self.language_context, "to_dict")
                else self.language_context
            ),
            "timeout_stage": self.timeout_stage,
            "timeout_stage_started_at": self.timeout_stage_started_at,
            "turn_id": self.turn_id,
            "lock_token": self.lock_token,
            "token": self.lock_token,
            "cancellation_requested": self.cancellation_requested,
        }


RuntimeTurnToken = RuntimeTurn


@dataclass(frozen=True)
class QueuedTurn:
    sequence: int
    owner: TurnOwner
    policy: BusyPolicy
    priority: int
    priority_name: str
    source: str
    conversation_id: str
    task_id: str
    step_id: str
    queued_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="milliseconds")
    )

    @property
    def sort_key(self):
        return (
            0 if self.policy is BusyPolicy.PREEMPT else 1,
            -self.priority,
            self.sequence,
        )

    def snapshot(self, position=0):
        return {
            "position": position,
            "owner": self.owner.value,
            "policy": self.policy.value,
            "priority": self.priority,
            "priority_name": self.priority_name,
            "source": self.source,
            "conversation_id": self.conversation_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "queued_at": self.queued_at,
            "sequence": self.sequence,
        }


class RuntimeTurnQueue:
    """Stable preempt/priority/FIFO queue for waiting turns."""

    def __init__(self):
        self._items = []
        self._sequence = count(1)

    def enqueue(self, **values):
        item = QueuedTurn(sequence=next(self._sequence), **values)
        self._items.append(item)
        self._items.sort(key=lambda queued: queued.sort_key)
        return item

    def remove(self, item):
        if item in self._items:
            self._items.remove(item)

    @property
    def head(self):
        return self._items[0] if self._items else None

    def __len__(self):
        return len(self._items)

    def snapshot(self):
        return [item.snapshot(index + 1) for index, item in enumerate(self._items)]

    def position(self, item):
        return self._items.index(item) + 1


class RuntimeBusyError(RuntimeError):
    def __init__(self, requested_owner, current_owner):
        self.requested_owner = TurnOwner(requested_owner)
        self.current_owner = TurnOwner(current_owner)
        super().__init__(
            f"Runtime is busy: owner={self.current_owner.value}, "
            f"requested={self.requested_owner.value}"
        )


class RuntimeTurnInterrupted(RuntimeError):
    pass


class RuntimeTurnLock:
    """Manage one active RuntimeTurn and an explicit ordered TurnQueue."""

    def __init__(self, on_acquired=None, on_released=None):
        self._condition = Condition(RLock())
        self._turn = None
        self._queue = RuntimeTurnQueue()
        self._turn_sequence = count(1)
        self._on_acquired = on_acquired
        self._on_released = on_released

    def acquire(
        self,
        owner,
        policy=BusyPolicy.REJECT,
        timeout=None,
        turn_timeout=None,
        soft_timeout=None,
        hard_timeout=None,
        priority=None,
        source="",
        conversation_id="",
        task_id="",
        step_id="",
    ):
        owner = TurnOwner(owner)
        policy = BusyPolicy(policy)
        priority_value, priority_name = self._priority(owner, priority)
        if hard_timeout is None:
            hard_timeout = turn_timeout
        if soft_timeout is not None and hard_timeout is not None:
            if float(soft_timeout) >= float(hard_timeout):
                raise ValueError("Soft timeout must be lower than hard timeout.")
        deadline = None if timeout is None else monotonic() + max(0.0, float(timeout))
        with self._condition:
            current = self._turn
            if current is not None and policy is BusyPolicy.REJECT:
                self._trace_busy(current, owner, policy)
                raise RuntimeBusyError(owner, current.owner)
            if current is not None and policy is BusyPolicy.PREEMPT:
                if priority_value <= current.priority:
                    self._trace_busy(current, owner, policy, reason="priority")
                    raise RuntimeBusyError(owner, current.owner)
                if not current.cancellation_requested:
                    current.request_cancellation()
                    trace_event(
                        "runtime.turn.preempt_requested",
                        owner=current.owner.value,
                        requested_owner=owner.value,
                        current_priority=current.priority,
                        requested_priority=priority_value,
                        turn_id=current.turn_id,
                        lock_token=current.lock_token,
                    )
            queued = None
            if self._turn is not None or len(self._queue):
                queued = self._queue.enqueue(
                    owner=owner,
                    policy=policy,
                    priority=priority_value,
                    priority_name=priority_name,
                    source=str(source or ""),
                    conversation_id=str(conversation_id or ""),
                    task_id=str(task_id or ""),
                    step_id=str(step_id or ""),
                )
                trace_event(
                    "runtime.lock.queued",
                    current_owner=self._turn.owner.value if self._turn else "",
                    **queued.snapshot(self._queue.position(queued)),
                    queued=len(self._queue),
                )
            try:
                while self._turn is not None or (
                    queued is not None and self._queue.head is not queued
                ):
                    remaining = None if deadline is None else deadline - monotonic()
                    if remaining is not None and remaining <= 0:
                        current_owner = self._turn.owner if self._turn else owner
                        if queued is not None:
                            self._queue.remove(queued)
                        self._trace_busy(
                            self._turn,
                            owner,
                            policy,
                            reason="preempt_timeout" if policy is BusyPolicy.PREEMPT else "timeout",
                            current_owner=current_owner,
                        )
                        self._condition.notify_all()
                        raise RuntimeBusyError(owner, current_owner)
                    self._condition.wait(remaining)
                if queued is not None:
                    self._queue.remove(queued)
                turn = RuntimeTurn(
                    owner=owner,
                    soft_timeout=self._seconds(soft_timeout),
                    hard_timeout=self._seconds(hard_timeout),
                    priority=priority_value,
                    priority_name=priority_name,
                    source=str(source or ""),
                    conversation_id=str(conversation_id or ""),
                    task_id=str(task_id or ""),
                    step_id=str(step_id or ""),
                    turn_id=f"TURN-{next(self._turn_sequence):06d}",
                )
                self._turn = turn
                self._start_timeout_timers(turn)
            except Exception:
                if queued is not None:
                    self._queue.remove(queued)
                raise
        trace_event(
            "runtime.lock.acquired",
            **turn.snapshot(),
            queued=len(self._queue),
            queue=self._queue.snapshot(),
        )
        if callable(self._on_acquired):
            try:
                self._on_acquired(turn)
            except Exception:
                self.release(turn, reason="acquire_callback_failed")
                raise
        return turn

    def release(self, turn, reason="completed"):
        if not isinstance(turn, RuntimeTurn):
            return False
        duration_ms = max(0, round((monotonic() - turn.acquired_at) * 1000))
        with self._condition:
            if self._turn is None or self._turn.lock_token != turn.lock_token:
                return False
            self._cancel_timeout_timers(turn)
            interrupted = turn.cancellation_requested
            turn.state = TurnState.INTERRUPTED if interrupted else self._terminal_state(reason)
            self._turn = None
            try:
                trace_event(
                    "runtime.lock.released",
                    **turn.snapshot(),
                    reason=str(reason or "completed"),
                    duration_ms=duration_ms,
                    queued=len(self._queue),
                    queue=self._queue.snapshot(),
                )
                if callable(self._on_released):
                    self._on_released(turn, reason)
            finally:
                self._condition.notify_all()
        return True

    def cancellation_requested(self, turn):
        return isinstance(turn, RuntimeTurn) and turn.cancellation_requested

    def set_timeout_stage(
        self,
        turn,
        stage,
        soft_timeout=None,
        hard_timeout=None,
    ):
        """Start a fresh timeout budget for one meaningful runtime stage."""
        if soft_timeout is not None and hard_timeout is not None:
            if float(soft_timeout) >= float(hard_timeout):
                raise ValueError("Soft timeout must be shorter than hard timeout.")
        with self._condition:
            if not isinstance(turn, RuntimeTurn) or self._turn is not turn:
                return False
            self._cancel_timeout_timers(turn)
            turn.soft_timeout = self._seconds(soft_timeout)
            turn.hard_timeout = self._seconds(hard_timeout)
            turn.timeout_stage = str(stage or "PROCESSING").upper()
            turn.timeout_stage_started_at = (
                datetime.now().astimezone().isoformat(timespec="milliseconds")
            )
            self._start_timeout_timers(turn)
            trace_event("runtime.turn.timeout_stage_changed", **turn.snapshot())
            return True

    def link_task(self, turn, task_id, step_id=""):
        """Attach Task/Step identity without merging their lifecycles."""
        with self._condition:
            if (
                not isinstance(turn, RuntimeTurn)
                or self._turn is None
                or self._turn.lock_token != turn.lock_token
            ):
                return False
            turn.task_id = str(task_id or "")
            turn.step_id = str(step_id or "")
            trace_event(
                "runtime.turn.task_linked",
                turn_id=turn.turn_id,
                task_id=turn.task_id,
                step_id=turn.step_id,
                owner=turn.owner.value,
            )
            return True

    @property
    def owner(self):
        with self._condition:
            return self._turn.owner if self._turn is not None else None

    @property
    def current_turn(self):
        with self._condition:
            return self._turn

    @property
    def queued(self):
        with self._condition:
            return len(self._queue)

    def snapshot(self):
        with self._condition:
            active = self._turn.snapshot() if self._turn else self._empty_turn()
            return {
                **active,
                "busy": self._turn is not None,
                "queued": len(self._queue),
                "queue": self._queue.snapshot(),
            }

    def _start_timeout_timers(self, turn):
        if turn.soft_timeout is not None:
            turn._soft_timer = Timer(turn.soft_timeout, self._soft_timeout, args=(turn,))
            turn._soft_timer.daemon = True
            turn._soft_timer.start()
        if turn.hard_timeout is not None:
            turn._hard_timer = Timer(turn.hard_timeout, self._hard_timeout, args=(turn,))
            turn._hard_timer.daemon = True
            turn._hard_timer.start()

    def _soft_timeout(self, turn):
        with self._condition:
            if self._turn is not turn:
                return
            trace_event("runtime.turn.timeout_warning", **turn.snapshot())

    def _hard_timeout(self, turn):
        with self._condition:
            if self._turn is not turn:
                return
            turn.request_cancellation()
            trace_event("runtime.turn.timeout", **turn.snapshot())
            self._condition.notify_all()

    @staticmethod
    def _cancel_timeout_timers(turn):
        for timer in (turn._soft_timer, turn._hard_timer):
            if timer is not None:
                timer.cancel()

    def _trace_busy(
        self,
        current,
        requested_owner,
        policy,
        reason="",
        current_owner=None,
    ):
        owner = current.owner if current is not None else current_owner
        trace_event(
            "runtime.lock.busy",
            owner=owner.value if owner is not None else "",
            requested_owner=requested_owner.value,
            policy=policy.value,
            reason=reason,
            queued=len(self._queue),
            queue=self._queue.snapshot(),
        )

    @staticmethod
    def _priority(owner, priority):
        if priority is None:
            member = DEFAULT_PRIORITY[owner]
            return int(member), member.name
        if isinstance(priority, TurnPriority):
            return int(priority), priority.name
        value = int(priority)
        try:
            return value, TurnPriority(value).name
        except ValueError:
            return value, "CUSTOM"

    @staticmethod
    def _seconds(value):
        return None if value is None else max(0.001, float(value))

    @staticmethod
    def _terminal_state(reason):
        return TurnState.FAILED if "fail" in str(reason or "").lower() else TurnState.COMPLETED

    @staticmethod
    def _empty_turn():
        return {
            "owner": "",
            "state": "",
            "started_at": "",
            "soft_timeout": None,
            "hard_timeout": None,
            "timeout": None,
            "priority": 0,
            "priority_name": "",
            "source": "",
            "conversation_id": "",
            "task_id": "",
            "step_id": "",
            "turn_id": "",
            "lock_token": "",
            "token": "",
            "cancellation_requested": False,
        }
