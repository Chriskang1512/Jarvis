from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class JarvisEventType(str, Enum):
    """Define event names that Jarvis modules can publish."""

    STATUS_CHANGED = "jarvis.status.changed"
    AGENT_STARTED = "jarvis.agent.started"
    AGENT_FINISHED = "jarvis.agent.finished"
    STT_STARTED = "jarvis.stt.started"
    STT_FINISHED = "jarvis.stt.finished"
    TTS_STARTED = "jarvis.tts.started"
    TTS_FINISHED = "jarvis.tts.finished"
    TOOL_STARTED = "jarvis.tool.started"
    TOOL_FINISHED = "jarvis.tool.finished"
    MEMORY_UPDATED = "jarvis.memory.updated"
    NOTIFICATION_CREATED = "jarvis.notification.created"


class JarvisStatus(str, Enum):
    """Define status values that describe what Jarvis is doing."""

    IDLE = "idle"
    WAKE = "wake"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WORKING = "working"
    SUCCESS = "success"
    ERROR = "error"


class JarvisEmotion(str, Enum):
    """Define simple emotion values for future renderers."""

    NEUTRAL = "neutral"
    FOCUSED = "focused"
    HAPPY = "happy"
    CONCERNED = "concerned"


@dataclass
class JarvisState:
    """Represent the current UI-independent state of Jarvis."""

    status: JarvisStatus
    emotion: JarvisEmotion = JarvisEmotion.NEUTRAL
    current_task: str = ""
    progress: int = 0
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class JarvisEvent:
    """Represent one event published through the Jarvis EventBus."""

    event_type: JarvisEventType
    state: JarvisState

    @property
    def name(self):
        """Return the event type for older code that reads event.name."""
        return self.event_type


def create_status_event(status, message):
    """Create a status changed event from a status and message."""
    state = JarvisState(status=status, message=message)
    return JarvisEvent(event_type=JarvisEventType.STATUS_CHANGED, state=state)


JarvisEventName = JarvisEventType
