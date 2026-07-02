import unittest

from jarvis.chat.providers import ClaudeProvider, MockChatProvider, OpenAIProvider


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


if __name__ == "__main__":
    unittest.main()
