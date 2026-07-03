from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from jarvis.memory import ConversationContext


@dataclass
class VoiceSession:
    """Track one voice interaction session."""

    session_id: str
    started_at: str
    conversation_context: ConversationContext
    turn_count: int = 0
    current_stage: str = "idle"
    interrupt_requested: bool = False

    def start_turn(self):
        """Mark that one new voice turn has started."""
        self.turn_count += 1
        self.current_stage = "wake"
        self.interrupt_requested = False

    def set_stage(self, stage):
        """Update the current voice pipeline stage."""
        self.current_stage = stage

    def request_interrupt(self):
        """Request that the current voice output should stop."""
        self.interrupt_requested = True

    def should_interrupt(self):
        """Return whether the current voice output should stop."""
        return self.interrupt_requested


def create_voice_session(max_turns=6, max_tokens=1200):
    """Create a fresh voice session."""
    return VoiceSession(
        session_id=create_session_id(),
        started_at=datetime.now().isoformat(timespec="seconds"),
        conversation_context=ConversationContext(
            max_turns=max_turns,
            max_tokens=max_tokens,
        ),
    )


def create_session_id():
    """Create a short readable voice session ID."""
    return str(uuid4()).split("-", 1)[0].upper()
