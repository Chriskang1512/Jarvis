import unittest
from dataclasses import fields

from jarvis.chat import ChatService, PromptBuilder, create_default_prompt_profile
from jarvis.chat.providers import (
    OPENAI_MODEL_CAPABILITY_CACHE,
    extract_api_error,
    mark_model_optional_generation_options_unsupported,
    minimal_generation_options,
    model_supports_optional_generation_options,
    removed_generation_options,
    should_retry_without_optional_generation_options,
)
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


class FakeOpenAIError(Exception):
    """Small API error stand-in for provider diagnostics tests."""

    def __init__(self):
        """Create a fake 400 response with a safe body shape."""
        super().__init__("400 Bad Request: unsupported parameter")
        self.status_code = 400
        self.body = {
            "error": {
                "type": "invalid_request_error",
                "code": "unsupported_parameter",
                "param": "reasoning",
                "message": "Unsupported parameter\nreasoning",
            }
        }


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

    def test_chat_provider_config_alias_selects_openai(self):
        """Check Beta.5 chat_provider config selects the OpenAI provider."""
        config = create_config_from_dict(
            {
                "chat_provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
            }
        )
        provider = create_llm_provider(config)
        metadata = provider.metadata()

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.chat_provider, "openai")
        self.assertEqual(metadata.id, "openai")

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

    def test_openai_api_error_extracts_safe_fields(self):
        """Check OpenAI error diagnostics capture useful non-secret fields."""
        api_error = extract_api_error(FakeOpenAIError())

        self.assertEqual(api_error["status"], 400)
        self.assertEqual(api_error["error_type"], "invalid_request_error")
        self.assertEqual(api_error["error_code"], "unsupported_parameter")
        self.assertEqual(api_error["error_param"], "reasoning")
        self.assertEqual(api_error["message"], "Unsupported parameter reasoning")

    def test_openai_generation_option_compatibility_helpers(self):
        """Check unsupported generation options are removed and cached."""
        OPENAI_MODEL_CAPABILITY_CACHE.clear()
        options = {
            "max_output_tokens": 300,
            "reasoning_effort": "minimal",
            "verbosity": "low",
        }
        retry_options = minimal_generation_options(options)

        self.assertEqual(retry_options, {"max_output_tokens": 300})
        self.assertEqual(removed_generation_options(options, retry_options), ["reasoning_effort", "verbosity"])
        self.assertTrue(should_retry_without_optional_generation_options(FakeOpenAIError(), options))
        self.assertTrue(model_supports_optional_generation_options("gpt-5.5"))

        mark_model_optional_generation_options_unsupported("gpt-5.5")

        self.assertFalse(model_supports_optional_generation_options("gpt-5.5"))


if __name__ == "__main__":
    unittest.main()
