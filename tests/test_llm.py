import unittest
from dataclasses import fields

from jarvis.chat import ChatService, PromptBuilder, create_default_prompt_profile
from jarvis.config.loader import create_config_from_dict
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.llm import LLMProviderFactory, create_llm_provider
from jarvis.llm.metadata import LLMProviderMetadata


class SimpleLLMProvider:
    """LLM provider used to verify ChatService contract usage."""

    def __init__(self):
        """Create provider state."""
        self.prompts = []
        self.last_metadata = None

    def generate(self, prompt):
        """Generate one response."""
        self.prompts.append(prompt)
        return "simple reply"

    def generate_stream(self, prompt):
        """Yield one response chunk."""
        yield self.generate(prompt)

    def metadata(self):
        """Return provider metadata."""
        return LLMProviderMetadata(
            id="simple",
            name="Simple",
            model="simple",
        )


class TestLLM(unittest.TestCase):
    """Test provider-independent LLM abstraction."""

    def test_mock_llm_provider_contract(self):
        """Check mock LLM provider supports the new contract."""
        provider = create_llm_provider(create_config_from_dict({"provider": "mock"}))

        reply = provider.generate("hello")
        metadata = provider.metadata()

        self.assertIsInstance(reply, str)
        self.assertEqual(metadata.id, "mock")
        self.assertFalse(metadata.supports_stream)

    def test_llm_provider_metadata_schema(self):
        """Lock the shared provider capability metadata contract."""
        field_names = [field.name for field in fields(LLMProviderMetadata)]

        self.assertEqual(
            field_names,
            [
                "id",
                "name",
                "model",
                "supports_stream",
                "supports_tools",
                "supports_images",
                "supports_reasoning",
            ],
        )

    def test_openai_llm_provider_contract_without_api_key(self):
        """Check OpenAI LLM provider contract without requiring an API key."""
        provider = create_llm_provider(
            create_config_from_dict(
                {
                    "provider": "openai",
                    "model": "gpt-5.5",
                    "temperature": 0.7,
                }
            )
        )

        reply = provider.generate("hello")
        metadata = provider.metadata()

        self.assertIsInstance(reply, str)
        self.assertEqual(metadata.id, "openai")
        self.assertTrue(metadata.supports_reasoning)

    def test_factory_publishes_provider_selected_event(self):
        """Check factory publishes provider selection diagnostics."""
        diagnostics = DiagnosticsCollector()
        factory = LLMProviderFactory(diagnostics_collector=diagnostics)

        factory.create(create_config_from_dict({"provider": "mock"}))

        snapshot = diagnostics.get_snapshot()
        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("llm.provider.selected", messages)
        self.assertEqual(snapshot.provider.provider_name, "mock")
        self.assertEqual(snapshot.provider.model, "mock")

    def test_chat_service_uses_generate_contract(self):
        """Check ChatService only needs provider.generate."""
        provider = SimpleLLMProvider()
        diagnostics = DiagnosticsCollector()
        service = ChatService(
            provider=provider,
            prompt_builder=PromptBuilder(create_default_prompt_profile()),
            diagnostics_collector=diagnostics,
        )

        reply = service.generate_reply("hello")

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertEqual(reply, "simple reply")
        self.assertEqual(len(provider.prompts), 1)
        self.assertIn("llm.request.started", messages)
        self.assertIn("llm.request.finished", messages)


if __name__ == "__main__":
    unittest.main()
