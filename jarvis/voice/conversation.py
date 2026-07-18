from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from uuid import uuid4


CONVERSATION_IDLE = "IDLE"
CONVERSATION_LISTENING = "LISTENING"
CONVERSATION_THINKING = "THINKING"
CONVERSATION_SPEAKING = "SPEAKING"
CONVERSATION_FOLLOW_UP = "FOLLOW_UP"
CONVERSATION_CLOSED = "CLOSED"
DEFAULT_LAST_MEMORY_RESULT_TURNS = 2
DEFAULT_PENDING_ACTION_TURNS = 2
DEFAULT_PENDING_ACTION_SECONDS = 30.0
DEFAULT_PENDING_CLARIFICATION_TURNS = 2
DEFAULT_PENDING_CLARIFICATION_SECONDS = 45.0


@dataclass
class ConversationSession:
    """Track one wake-word conversation lifecycle."""

    session_id: str
    started_at: str
    last_activity: str
    state: str = CONVERSATION_IDLE
    follow_up_timeout: float = 0.0
    last_activity_time: float = 0.0
    last_memory_result: dict | None = None
    last_memory_result_turns_remaining: int = 0
    last_calendar_result: dict | None = None
    last_calendar_event: dict | None = None
    last_reminder: dict | None = None
    last_task: dict | None = None
    pending_action: dict | None = None
    pending_action_turns_remaining: int = 0
    pending_action_expires_at: float = 0.0
    pending_clarification: dict | None = None
    pending_clarification_turns_remaining: int = 0
    pending_clarification_expires_at: float = 0.0
    conversation_task: object | None = None

    def start(self):
        """Mark the conversation as listening."""
        self.transition(CONVERSATION_LISTENING)

    def transition(self, state):
        """Move the session to a new state and refresh activity time."""
        self.state = state
        self.last_activity = current_timestamp()
        self.last_activity_time = perf_counter()

    def enter_follow_up(self):
        """Move to follow-up listening state."""
        self.transition(CONVERSATION_FOLLOW_UP)

    def close(self):
        """Close the conversation session."""
        self.clear_last_memory_result()
        self.clear_last_calendar_result()
        self.clear_last_reminder()
        self.clear_last_task()
        self.clear_pending_action()
        self.clear_pending_clarification()
        self.clear_conversation_task()
        self.transition(CONVERSATION_CLOSED)

    def set_last_memory_result(self, memory_result, turns=DEFAULT_LAST_MEMORY_RESULT_TURNS):
        """Keep one memory result only inside this wake session."""
        self.last_memory_result = dict(memory_result)
        self.last_memory_result_turns_remaining = max(0, int(turns))

    def get_last_memory_result(self):
        """Return the session-scoped memory result while it is still valid."""
        if self.last_memory_result_turns_remaining <= 0:
            self.clear_last_memory_result()
            return None

        return self.last_memory_result

    def advance_memory_result_turn(self):
        """Age the session-scoped memory result by one follow-up turn."""
        if self.last_memory_result is None:
            return

        self.last_memory_result_turns_remaining -= 1

        if self.last_memory_result_turns_remaining <= 0:
            self.clear_last_memory_result()

    def clear_last_memory_result(self):
        """Clear session-scoped memory context."""
        self.last_memory_result = None
        self.last_memory_result_turns_remaining = 0

    def set_last_calendar_result(self, calendar_result):
        """Keep the last CalendarResult inside this wake session."""
        self.last_calendar_result = dict(calendar_result)

    def set_last_calendar_event(self, calendar_event):
        """Keep the last selected Calendar event inside this wake session."""
        self.last_calendar_event = dict(calendar_event)

    def get_last_calendar_event(self):
        """Return the last selected Calendar event."""
        return self.last_calendar_event

    def get_last_calendar_result(self):
        """Return session-scoped calendar context."""
        return self.last_calendar_result

    def clear_last_calendar_result(self):
        """Clear session-scoped calendar context."""
        self.last_calendar_result = None
        self.last_calendar_event = None

    def set_last_reminder(self, reminder):
        """Keep the last Reminder inside this wake session."""
        self.last_reminder = dict(reminder)

    def get_last_reminder(self):
        """Return the last Reminder context."""
        return self.last_reminder

    def clear_last_reminder(self):
        """Clear session-scoped Reminder context."""
        self.last_reminder = None

    def set_last_task(self, task):
        """Keep the last RuntimeTask inside this wake session."""
        self.last_task = dict(task)

    def get_last_task(self):
        """Return the last RuntimeTask context."""
        return self.last_task

    def clear_last_task(self):
        """Clear session-scoped RuntimeTask context."""
        self.last_task = None

    def set_pending_action(
        self,
        pending_action,
        turns=DEFAULT_PENDING_ACTION_TURNS,
        seconds=DEFAULT_PENDING_ACTION_SECONDS,
    ):
        """Keep one confirmation action inside this wake session."""
        self.pending_action = dict(pending_action)
        self.pending_action_turns_remaining = max(0, int(turns))
        self.pending_action_expires_at = perf_counter() + float(seconds)

    def get_pending_action(self):
        """Return pending action if it has not expired."""
        if self.pending_action is None:
            return None

        if self.pending_action_turns_remaining <= 0 or perf_counter() > self.pending_action_expires_at:
            self.clear_pending_action()
            return None

        return self.pending_action

    def advance_pending_action_turn(self):
        """Age pending confirmation by one follow-up attempt."""
        if self.pending_action is None:
            return

        self.pending_action_turns_remaining -= 1

        if self.pending_action_turns_remaining <= 0:
            self.clear_pending_action()

    def clear_pending_action(self):
        """Clear pending confirmation action."""
        self.pending_action = None
        self.pending_action_turns_remaining = 0
        self.pending_action_expires_at = 0.0

    def set_pending_clarification(
        self,
        pending_clarification,
        turns=DEFAULT_PENDING_CLARIFICATION_TURNS,
        seconds=DEFAULT_PENDING_CLARIFICATION_SECONDS,
    ):
        """Keep one clarification request inside this wake session."""
        self.pending_clarification = dict(pending_clarification)
        self.pending_clarification_turns_remaining = max(0, int(turns))
        self.pending_clarification_expires_at = perf_counter() + float(seconds)

    def get_pending_clarification(self):
        """Return pending clarification if it has not expired."""
        if self.pending_clarification is None:
            return None

        if self.pending_clarification_turns_remaining <= 0 or perf_counter() > self.pending_clarification_expires_at:
            self.clear_pending_clarification()
            return None

        return self.pending_clarification

    def advance_pending_clarification_turn(self):
        """Age pending clarification by one follow-up attempt."""
        if self.pending_clarification is None:
            return

        self.pending_clarification_turns_remaining -= 1

        if self.pending_clarification_turns_remaining <= 0:
            self.clear_pending_clarification()

    def clear_pending_clarification(self):
        """Clear pending clarification state."""
        self.pending_clarification = None
        self.pending_clarification_turns_remaining = 0
        self.pending_clarification_expires_at = 0.0

    def set_conversation_task(self, conversation_task):
        """Store one active multi-turn runtime task."""
        self.conversation_task = conversation_task

    def get_conversation_task(self):
        """Return the active conversation task if it has not expired."""
        if self.conversation_task is None:
            return None

        if hasattr(self.conversation_task, "is_expired") and self.conversation_task.is_expired():
            if hasattr(self.conversation_task, "task_state"):
                self.conversation_task.task_state = "expired"
            if hasattr(self.conversation_task, "state"):
                self.conversation_task.state = "EXPIRED"
            expired_task = self.conversation_task
            self.clear_conversation_task()
            return expired_task

        return self.conversation_task

    def clear_conversation_task(self):
        """Clear the active multi-turn runtime task."""
        self.conversation_task = None

    def remaining_follow_up_seconds(self, now=None):
        """Return remaining follow-up seconds."""
        if self.follow_up_timeout <= 0:
            return 0.0

        current_time = perf_counter() if now is None else now
        elapsed = current_time - self.last_activity_time
        return max(0.0, self.follow_up_timeout - elapsed)

    def is_follow_up_expired(self, now=None):
        """Return whether the follow-up window has expired."""
        return self.remaining_follow_up_seconds(now=now) <= 0.0

    def to_dict(self):
        """Return a stable diagnostics payload."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_activity": self.last_activity,
            "state": self.state,
            "follow_up_timeout": self.follow_up_timeout,
            "remaining": self.remaining_follow_up_seconds(),
            "last_memory_result": self.last_memory_result,
            "last_memory_result_turns_remaining": self.last_memory_result_turns_remaining,
            "last_calendar_result": self.last_calendar_result,
            "last_calendar_event": self.last_calendar_event,
            "last_reminder": self.last_reminder,
            "last_task": self.last_task,
            "pending_action": self.pending_action,
            "pending_action_turns_remaining": self.pending_action_turns_remaining,
            "pending_clarification": self.pending_clarification,
            "pending_clarification_turns_remaining": self.pending_clarification_turns_remaining,
            "conversation_task": conversation_task_to_dict(self.conversation_task),
        }


def create_conversation_session(follow_up_timeout=0.0):
    """Create one fresh conversation session."""
    timestamp = current_timestamp()
    now = perf_counter()
    return ConversationSession(
        session_id=create_conversation_id(),
        started_at=timestamp,
        last_activity=timestamp,
        state=CONVERSATION_IDLE,
        follow_up_timeout=float(follow_up_timeout),
        last_activity_time=now,
    )


def create_conversation_id():
    """Create a short readable conversation session ID."""
    return uuid4().hex[:8].upper()


def current_timestamp():
    """Return local ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def conversation_task_to_dict(conversation_task):
    """Return compact diagnostics for a conversation task."""
    if conversation_task is None:
        return None

    return {
        "id": getattr(conversation_task, "id", ""),
        "task_state": getattr(conversation_task, "task_state", ""),
        "state": getattr(conversation_task, "state", ""),
        "missing_fields": list(getattr(conversation_task, "missing_fields", []) or []),
        "pending_clarification": getattr(conversation_task, "pending_clarification", ""),
        "conversation_turn": getattr(conversation_task, "conversation_turn", 0),
        "expires_turns": getattr(conversation_task, "expires_turns", 0),
        "last_updated": getattr(conversation_task, "last_updated", ""),
    }
