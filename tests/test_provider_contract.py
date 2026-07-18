import sys
import unittest
from types import SimpleNamespace

from jarvis.chat.providers import ClaudeProvider, MockChatProvider, OpenAIChatProvider, OpenAIProvider


class TestProviderContract(unittest.TestCase):
    """Test that all chat providers keep the same public contract."""

    def test_mock_provider_contract(self):
        """Check that MockChatProvider returns text and metadata."""
        provider = MockChatProvider()

        self.assert_provider_contract(provider, "mock")

    def test_openai_provider_contract_without_api_key(self):
        """Check that OpenAIProvider keeps contract without an API key."""
        provider = OpenAIProvider(
            model="gpt-5.5",
            temperature=0.7,
            env_path=".env.test.missing",
        )

        self.assert_provider_contract(provider, "openai")

    def test_openai_chat_provider_uses_mocked_sdk_response(self):
        """Check OpenAIChatProvider can generate without a real API call."""
        fake_module = SimpleNamespace(OpenAI=FakeOpenAIClient)
        original_module = sys.modules.get("openai")
        sys.modules["openai"] = fake_module

        try:
            provider = OpenAIChatProvider(
                model="gpt-4o-mini",
                temperature=0.2,
                api_key_reader=lambda env_path: "test-key",
            )

            reply = provider.generate_reply("hello")
        finally:
            if original_module is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = original_module

        request = FakeOpenAIClient.last_request
        self.assertEqual(reply, "안녕하세요! 무엇을 도와드릴까요?")
        self.assertEqual(provider.last_metadata.provider_name, "openai")
        self.assertEqual(provider.last_metadata.model, "gpt-4o-mini")
        self.assertEqual(request["input"], "hello")
        self.assertNotIn("tools", request)
        self.assertNotIn("stream", request)

    def test_claude_provider_contract_without_api_key(self):
        """Check that ClaudeProvider keeps contract without an API key."""
        provider = ClaudeProvider(
            model="claude-opus-4-6",
            temperature=0.7,
            env_path=".env.test.missing",
        )

        self.assert_provider_contract(provider, "claude")

    def assert_provider_contract(self, provider, expected_provider_name):
        """Check the shared ChatProvider contract."""
        reply = provider.generate_reply("hello")

        self.assertIsInstance(reply, str)
        self.assertTrue(hasattr(provider, "last_metadata"))
        self.assertTrue(hasattr(provider.last_metadata, "provider_name"))
        self.assertTrue(hasattr(provider.last_metadata, "model"))
        self.assertTrue(hasattr(provider.last_metadata, "finish_reason"))
        self.assertTrue(hasattr(provider.last_metadata, "usage"))
        self.assertEqual(provider.last_metadata.provider_name, expected_provider_name)
        self.assertIsInstance(provider.last_metadata.model, str)


class FakeOpenAIClient:
    """Minimal fake OpenAI SDK client."""

    last_request = {}

    def __init__(self, api_key):
        """Capture the fake API key."""
        self.api_key = api_key
        self.responses = FakeOpenAIResponses()


class FakeOpenAIResponses:
    """Fake responses resource."""

    def create(self, **request_data):
        """Return a deterministic fake response."""
        FakeOpenAIClient.last_request = request_data
        return SimpleNamespace(
            output_text="안녕하세요! 무엇을 도와드릴까요?",
            model=request_data["model"],
            finish_reason="stop",
            usage={"input_tokens": 1, "output_tokens": 1},
        )


if __name__ == "__main__":
    unittest.main()
