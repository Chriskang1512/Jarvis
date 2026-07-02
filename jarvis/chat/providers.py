from typing import Protocol


class ChatProvider(Protocol):
    """Interface for future chat providers such as OpenAI or Claude."""

    def generate_reply(self, message):
        """Generate one reply for a user message."""
        ...


class MockChatProvider:
    """Simple local chat provider used before real AI APIs are connected."""

    def generate_reply(self, message):
        """Return a fixed response without using network or API keys."""
        if message.strip() == "":
            return "무엇을 이야기할까요?"

        return "안녕하세요.\n저는 Jarvis입니다."

