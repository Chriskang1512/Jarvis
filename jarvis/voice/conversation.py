from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from uuid import uuid4

from jarvis.runtime.conversation_resolver import ConversationResolver
from jarvis.runtime.task import RuntimeTask


CONVERSATION_IDLE = "IDLE"
CONVERSATION_LISTENING = "LISTENING"
CONVERSATION_THINKING = "THINKING"
CONVERSATION_SPEAKING = "SPEAKING"
CONVERSATION_FOLLOW_UP = "FOLLOW_UP"
CONVERSATION_CLOSED = "CLOSED"
DEFAULT_LAST_MEMORY_RESULT_TURNS = 2
DEFAULT_PENDING_ACTION_TURNS = 2
DEFAULT_PENDING_ACTION_SECONDS = 120.0
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
    runtime_task: RuntimeTask | None = None
    resolver: ConversationResolver = field(default_factory=ConversationResolver, repr=False)

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

    def close(self, preserve_context=False):
        """Close the conversation session."""
        if preserve_context:
            self.transition(CONVERSATION_CLOSED)
            return
        self.clear_last_memory_result()
        self.clear_last_calendar_result()
        self.clear_last_reminder()
        self.clear_last_task()
        self.cleanup_conversation_context()
        self.transition(CONVERSATION_CLOSED)

    def set_last_memory_result(self, memory_result, turns=DEFAULT_LAST_MEMORY_RESULT_TURNS):
        """Keep one memory result only inside this wake session."""
        self.runtime_task = self.resolver.select(
            self.ensure_runtime_task(),
            "last_memory_result",
            dict(memory_result),
        )
        self.runtime_task = self.resolver.select(
            self.runtime_task,
            "last_memory_result_turns_remaining",
            max(0, int(turns)),
        )

    def get_last_memory_result(self):
        """Return the session-scoped memory result while it is still valid."""
        if self.last_memory_result_turns_remaining <= 0:
            self.clear_last_memory_result()
            return None

        return self.resolver.selected(self.ensure_runtime_task(), "last_memory_result")

    def advance_memory_result_turn(self):
        """Age the session-scoped memory result by one follow-up turn."""
        if self.get_last_memory_result() is None:
            return

        remaining = self.last_memory_result_turns_remaining - 1
        self.runtime_task = self.resolver.select(
            self.ensure_runtime_task(),
            "last_memory_result_turns_remaining",
            remaining,
        )
        if remaining <= 0:
            self.clear_last_memory_result()

    def clear_last_memory_result(self):
        """Clear session-scoped memory context."""
        self.clear_selected_entity("last_memory_result")
        self.clear_selected_entity("last_memory_result_turns_remaining")

    def set_last_calendar_result(self, calendar_result):
        """Keep the last CalendarResult inside this wake session."""
        self.runtime_task = self.resolver.select(
            self.ensure_runtime_task(),
            "last_calendar_result",
            dict(calendar_result),
        )

    def set_last_calendar_event(self, calendar_event):
        """Keep the last selected Calendar event inside this wake session."""
        self.runtime_task = self.resolver.select(
            self.ensure_runtime_task(),
            "last_calendar_event",
            dict(calendar_event),
        )

    def get_last_calendar_event(self):
        """Return the last selected Calendar event."""
        return self.resolver.selected(self.ensure_runtime_task(), "last_calendar_event")

    def get_last_calendar_result(self):
        """Return session-scoped calendar context."""
        return self.resolver.selected(self.ensure_runtime_task(), "last_calendar_result")

    def clear_last_calendar_result(self):
        """Clear session-scoped calendar context."""
        self.clear_selected_entity("last_calendar_result")
        self.clear_selected_entity("last_calendar_event")

    def set_last_reminder(self, reminder):
        """Keep the last Reminder inside this wake session."""
        self.runtime_task = self.resolver.select(
            self.ensure_runtime_task(),
            "last_reminder",
            dict(reminder),
        )

    def get_last_reminder(self):
        """Return the last Reminder context."""
        return self.resolver.selected(self.ensure_runtime_task(), "last_reminder")

    def clear_last_reminder(self):
        """Clear session-scoped Reminder context."""
        self.clear_selected_entity("last_reminder")

    def set_last_task(self, task):
        """Keep the last RuntimeTask inside this wake session."""
        self.runtime_task = self.resolver.select(
            self.ensure_runtime_task(),
            "last_task",
            dict(task),
        )

    def get_last_task(self):
        """Return the last RuntimeTask context."""
        return self.resolver.selected(self.ensure_runtime_task(), "last_task")

    def clear_last_task(self):
        """Clear session-scoped RuntimeTask context."""
        self.clear_selected_entity("last_task")

    def set_pending_action(
        self,
        pending_action,
        turns=DEFAULT_PENDING_ACTION_TURNS,
        seconds=DEFAULT_PENDING_ACTION_SECONDS,
    ):
        """Store one confirmation action on the active RuntimeTask."""
        task = self.ensure_runtime_task(goal=format_pending_goal(pending_action))
        task = self.resolver.set_question(
            task,
            "confirmation",
            payload=dict(pending_action),
            turns=turns,
            seconds=seconds,
        )
        task = self.resolver.add_artifact(
            task,
            artifact_type="pending_action",
            artifact_id=str(pending_action.get("task_id", "") or task.id),
            payload=dict(pending_action),
        )
        self.runtime_task = self.resolver.set_confirmation(task, "PENDING")

    def get_pending_action(self):
        """Return pending action if it has not expired."""
        question = self.resolver.get_question(self.ensure_runtime_task())
        if question is None or question.kind != "confirmation":
            return None
        return dict(question.payload)

    def advance_pending_action_turn(self):
        """Age pending confirmation by one follow-up attempt."""
        question = self.resolver.get_question(self.ensure_runtime_task())
        if question is None or question.kind != "confirmation":
            return
        self.runtime_task = self.resolver.advance_question(self.runtime_task)

    def clear_pending_action(self):
        """Clear pending confirmation action."""
        task = self.ensure_runtime_task()
        question = self.resolver.get_question(task)
        if question is not None and question.kind == "confirmation":
            task = self.resolver.clear_question(task)
        self.runtime_task = self.resolver.set_confirmation(task, "")

    def answer_pending_action(self, answer):
        """Resolve the Runtime-owned confirmation question."""
        task = self.ensure_runtime_task()
        self.runtime_task = self.resolver.set_confirmation(
            self.resolver.answer_question(task, answer),
            str(answer or "").upper(),
        )

    def complete_pending_action(self):
        """Drop the confirmed draft while retaining follow-up selections."""
        task = self.ensure_runtime_task()
        artifacts = tuple(
            item
            for item in task.conversation_context.pending_artifacts
            if item.artifact_type != "pending_action"
        )
        task = self.resolver.update_context(task, pending_artifacts=artifacts)
        self.runtime_task = self.resolver.set_confirmation(task, "COMPLETED")

    def set_pending_clarification(
        self,
        pending_clarification,
        turns=DEFAULT_PENDING_CLARIFICATION_TURNS,
        seconds=DEFAULT_PENDING_CLARIFICATION_SECONDS,
    ):
        """Store one clarification request on the active RuntimeTask."""
        task = self.ensure_runtime_task(goal="clarification")
        self.runtime_task = self.resolver.set_question(
            task,
            str(pending_clarification.get("kind", "") or "clarification"),
            payload=dict(pending_clarification),
            text=str(pending_clarification.get("question", "") or ""),
            turns=turns,
            seconds=seconds,
        )

    def get_pending_clarification(self):
        """Return pending clarification if it has not expired."""
        question = self.resolver.get_question(self.ensure_runtime_task())
        if question is None or question.kind == "confirmation":
            return None
        return dict(question.payload)

    def advance_pending_clarification_turn(self):
        """Age pending clarification by one follow-up attempt."""
        question = self.resolver.get_question(self.ensure_runtime_task())
        if question is None or question.kind == "confirmation":
            return
        self.runtime_task = self.resolver.advance_question(self.runtime_task)

    def clear_pending_clarification(self):
        """Clear pending clarification state."""
        task = self.ensure_runtime_task()
        question = self.resolver.get_question(task)
        if question is not None and question.kind != "confirmation":
            self.runtime_task = self.resolver.clear_question(task)

    def answer_pending_clarification(self, answer):
        """Resolve the Runtime-owned clarification question."""
        self.runtime_task = self.resolver.answer_question(self.ensure_runtime_task(), answer)

    def set_conversation_task(self, conversation_task):
        """Store a legacy collected form as a RuntimeTask artifact."""
        task = self.ensure_runtime_task(goal="calendar conversation")
        self.runtime_task = self.resolver.add_artifact(
            task,
            artifact_type="calendar_conversation",
            artifact_id=str(getattr(conversation_task, "id", "") or task.id),
            payload=conversation_task,
        )

    def get_conversation_task(self):
        """Return the active conversation task if it has not expired."""
        artifact = self.resolver.artifact(self.ensure_runtime_task(), "calendar_conversation")
        conversation_task = artifact.payload if artifact is not None else None
        if conversation_task is None:
            return None

        if hasattr(conversation_task, "is_expired") and conversation_task.is_expired():
            if hasattr(conversation_task, "task_state"):
                conversation_task.task_state = "expired"
            if hasattr(conversation_task, "state"):
                conversation_task.state = "EXPIRED"
            expired_task = conversation_task
            self.clear_conversation_task()
            return expired_task

        return conversation_task

    def clear_conversation_task(self):
        """Clear the active multi-turn runtime task."""
        task = self.ensure_runtime_task()
        artifacts = tuple(
            item
            for item in task.conversation_context.pending_artifacts
            if item.artifact_type != "calendar_conversation"
        )
        self.runtime_task = self.resolver.update_context(task, pending_artifacts=artifacts)

    def bind_runtime_task(self, task):
        """Make an execution RuntimeTask the owner of subsequent conversation state."""
        if task is not None and self.runtime_task is None:
            self.runtime_task = task
        elif task is not None:
            self.runtime_task = self.resolver.select(
                self.runtime_task,
                "last_execution_task_id",
                getattr(task, "id", ""),
            )
        return self.runtime_task

    def ensure_runtime_task(self, goal=""):
        self.runtime_task = self.resolver.ensure_task(self.runtime_task, goal=goal)
        return self.runtime_task

    def cleanup_conversation_context(self):
        """Remove all transient selections, questions, and artifacts."""
        self.runtime_task = self.resolver.cleanup(self.ensure_runtime_task())

    def clear_selected_entity(self, key):
        task = self.ensure_runtime_task()
        selected = dict(task.conversation_context.selected_entities)
        selected.pop(str(key), None)
        self.runtime_task = self.resolver.update_context(task, selected_entities=selected)

    @property
    def last_memory_result(self):
        return self.resolver.selected(self.ensure_runtime_task(), "last_memory_result")

    @property
    def last_memory_result_turns_remaining(self):
        return int(
            self.resolver.selected(
                self.ensure_runtime_task(),
                "last_memory_result_turns_remaining",
                0,
            )
            or 0
        )

    @property
    def last_calendar_result(self):
        return self.resolver.selected(self.ensure_runtime_task(), "last_calendar_result")

    @property
    def last_calendar_event(self):
        return self.resolver.selected(self.ensure_runtime_task(), "last_calendar_event")

    @property
    def last_reminder(self):
        return self.resolver.selected(self.ensure_runtime_task(), "last_reminder")

    @property
    def last_task(self):
        return self.resolver.selected(self.ensure_runtime_task(), "last_task")

    @property
    def pending_action(self):
        return self.get_pending_action()

    @property
    def pending_action_turns_remaining(self):
        question = self.resolver.get_question(self.ensure_runtime_task())
        return question.turns_remaining if question is not None and question.kind == "confirmation" else 0

    @property
    def pending_clarification(self):
        return self.get_pending_clarification()

    @property
    def pending_clarification_turns_remaining(self):
        question = self.resolver.get_question(self.ensure_runtime_task())
        return question.turns_remaining if question is not None and question.kind != "confirmation" else 0

    @property
    def conversation_task(self):
        return self.get_conversation_task()

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
            "conversation_task": conversation_task_to_dict(self.get_conversation_task()),
            "runtime_task_id": getattr(self.runtime_task, "id", ""),
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


def format_pending_goal(pending_action):
    return ".".join(
        item
        for item in (
            str(pending_action.get("ability", "") or ""),
            str(pending_action.get("action", "") or ""),
        )
        if item
    ) or "confirmation"
