from jarvis.memory import ConversationContext


class ChatService:
    """Conversation service that hides the concrete ChatProvider."""

    def __init__(
        self,
        provider,
        prompt_builder,
        memory_service=None,
        conversation_context=None,
        voice_session=None,
        diagnostics_collector=None,
    ):
        """Create a chat service with injected providers and optional context."""
        self.provider = provider
        self.prompt_builder = prompt_builder
        self.memory_service = memory_service
        self.voice_session = voice_session
        self.conversation_context = select_conversation_context(
            conversation_context=conversation_context,
            voice_session=voice_session,
        )
        self.diagnostics_collector = diagnostics_collector

    def generate_reply(self, message):
        """Build a prompt and ask the provider to generate a reply."""
        self.start_conversation()

        if self.memory_service is not None:
            key, value = extract_memory_fact(message)

            if key != "":
                self.memory_service.remember(key, value)
                reply = "I will remember that."
                self.update_conversation(message, reply)
                return reply

            recall_key = extract_recall_key(message)

            if recall_key != "":
                memory_value = self.memory_service.recall(recall_key)
                reply = format_memory_reply(recall_key, memory_value)
                self.update_conversation(message, reply)
                return reply

        history = self.conversation_context.build_history()
        if history != "":
            self.log_event("conversation.context.injected")

        prompt = self.prompt_builder.build(message, conversation_history=history)
        reply = self.provider.generate_reply(prompt)
        self.update_conversation(message, reply)
        return reply

    def finish_conversation(self):
        """Mark the active conversation as finished."""
        if self.conversation_context.finish():
            self.log_event("conversation.finished")

    def start_conversation(self):
        """Start the current conversation when needed."""
        if self.conversation_context.start():
            self.log_event("conversation.started")

    def update_conversation(self, message, reply):
        """Store one user/assistant turn in short-term context."""
        self.conversation_context.add_turn(message, reply)
        self.log_event("conversation.updated")

    def log_event(self, message):
        """Publish a diagnostics event when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def extract_memory_fact(message):
    """Extract a simple memory key and value from a user message."""
    english_name = extract_value_after_marker_case_insensitive(message, "my name is")

    if english_name != "":
        return "user_name", clean_name(english_name)

    korean_name = extract_value_after_marker(message, "my name:")

    if korean_name != "":
        return "user_name", clean_name(korean_name)

    return "", ""


def extract_recall_key(message):
    """Return the memory key requested by a user message."""
    lowered_message = message.lower()
    english_keywords = ["what is my name", "what's my name", "remember my name"]

    if any(keyword in lowered_message for keyword in english_keywords):
        return "user_name"

    return ""


def select_conversation_context(conversation_context=None, voice_session=None):
    """Return the active session conversation context."""
    if conversation_context is not None:
        return conversation_context

    if voice_session is not None:
        return voice_session.conversation_context

    return ConversationContext()


def extract_value_after_marker(message, marker):
    """Extract text that appears after one marker."""
    if marker not in message:
        return ""

    return message.split(marker, 1)[1].strip()


def extract_value_after_marker_case_insensitive(message, marker):
    """Extract text after one marker while preserving original casing."""
    lowered_message = message.lower()

    if marker not in lowered_message:
        return ""

    marker_index = lowered_message.index(marker)
    value_start = marker_index + len(marker)
    return message[value_start:].strip()


def clean_name(name):
    """Clean common English sentence endings from a name."""
    endings = [".", "!", "?", " please"]

    for ending in endings:
        if name.lower().endswith(ending):
            return name[: -len(ending)].strip()

    return name.strip()


def format_memory_reply(key, value):
    """Format one recalled memory value for the user."""
    if key == "user_name" and value != "":
        return f"Your name is {value}."

    if key == "user_name":
        return "I do not know your name yet."

    return ""
