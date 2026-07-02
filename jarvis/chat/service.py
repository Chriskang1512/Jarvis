class ChatService:
    """Conversation service that hides the concrete ChatProvider."""

    def __init__(self, provider, prompt_builder, memory_service=None):
        """Create a chat service with injected provider and optional memory."""
        self.provider = provider
        self.prompt_builder = prompt_builder
        self.memory_service = memory_service

    def generate_reply(self, message):
        """Build a prompt and ask the provider to generate a reply."""
        if self.memory_service is not None:
            key, value = extract_memory_fact(message)

            if key != "":
                self.memory_service.remember(key, value)
                return "기억했습니다."

            recall_key = extract_recall_key(message)

            if recall_key != "":
                memory_value = self.memory_service.recall(recall_key)
                return format_memory_reply(recall_key, memory_value)

        prompt = self.prompt_builder.build(message)
        return self.provider.generate_reply(prompt)


def extract_memory_fact(message):
    """Extract a simple memory key and value from a user message."""
    korean_name = extract_value_after_marker(message, "내 이름은")

    if korean_name != "":
        return "user_name", clean_name(korean_name)

    english_name = extract_value_after_marker_case_insensitive(message, "my name is")

    if english_name != "":
        return "user_name", clean_name(english_name)

    return "", ""


def extract_recall_key(message):
    """Return the memory key requested by a user message."""
    lowered_message = message.lower()
    korean_keywords = ["내 이름", "이름이 뭐", "이름 기억"]
    english_keywords = ["what is my name", "what's my name", "remember my name"]

    if any(keyword in message for keyword in korean_keywords):
        return "user_name"

    if any(keyword in lowered_message for keyword in english_keywords):
        return "user_name"

    return ""


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
    """Clean common Korean and English sentence endings from a name."""
    endings = ["이야.", "야.", "입니다.", "이에요.", "예요.", "이야", "야", "."]

    for ending in endings:
        if name.endswith(ending):
            return name[: -len(ending)].strip()

    return name.strip()


def format_memory_reply(key, value):
    """Format one recalled memory value for the user."""
    if key == "user_name" and value != "":
        return f"{value}입니다."

    if key == "user_name":
        return "아직 이름을 기억하지 못했습니다."

    return ""
