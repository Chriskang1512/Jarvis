from dataclasses import dataclass


@dataclass
class ConversationTurn:
    """Store one short-term conversation turn."""

    user_message: str
    assistant_message: str


class ConversationContext:
    """Keep recent conversation turns for the current Jarvis session."""

    def __init__(self, max_turns=6, max_tokens=1200):
        """Create a bounded short-term conversation context."""
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.turns = []
        self.started = False
        self.finished = False

    def start(self):
        """Mark the conversation as started."""
        if self.started:
            return False

        self.started = True
        self.finished = False
        return True

    def add_turn(self, user_message, assistant_message):
        """Add one turn and keep the history inside the configured window."""
        self.start()
        self.turns.append(
            ConversationTurn(
                user_message=user_message,
                assistant_message=assistant_message,
            )
        )
        self.trim()

    def get_recent_turns(self):
        """Return a copy of the currently retained turns."""
        return list(self.turns)

    def build_history(self):
        """Return provider-ready conversation history text."""
        if len(self.turns) == 0:
            return ""

        lines = []

        for turn in self.turns:
            lines.append(f"User: {turn.user_message}")
            lines.append(f"Assistant: {turn.assistant_message}")

        return "\n".join(lines)

    def finish(self):
        """Mark the conversation as finished."""
        if not self.started or self.finished:
            return False

        self.finished = True
        return True

    def clear(self):
        """Clear the current short-term history."""
        self.turns = []
        self.started = False
        self.finished = False

    def trim(self):
        """Keep only the most recent turns and token window."""
        if self.max_turns > 0:
            self.turns = self.turns[-self.max_turns :]

        while self.max_tokens > 0 and self.estimated_token_count() > self.max_tokens:
            if len(self.turns) <= 1:
                break

            self.turns.pop(0)

    def estimated_token_count(self):
        """Estimate token count for the retained history."""
        return estimate_tokens(self.build_history())


def estimate_tokens(text):
    """Return a lightweight token estimate without provider dependencies."""
    if text == "":
        return 0

    return max(1, len(text) // 4)
