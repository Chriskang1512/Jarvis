from jarvis.chat.providers import ClaudeProvider
from jarvis.llm.providers import MockLLMProvider, OpenAILLMProvider


class LLMProviderFactory:
    """Create LLM providers from runtime configuration."""

    def __init__(self, diagnostics_collector=None):
        """Create a factory with optional diagnostics."""
        self.diagnostics_collector = diagnostics_collector

    def create(self, config):
        """Return an LLM provider for the configured provider name."""
        provider = create_llm_provider(config)
        self.log_selected(provider)
        return provider

    def log_selected(self, provider):
        """Publish provider selection diagnostics."""
        if self.diagnostics_collector is None:
            return

        metadata = get_provider_metadata(provider)
        if metadata is not None:
            self.diagnostics_collector.publish_provider(
                provider_name=metadata.id,
                model=metadata.model,
            )

        self.diagnostics_collector.log_event("llm.provider.selected")


def create_llm_provider(config):
    """Create an LLM provider from config."""
    if config.provider == "mock":
        return MockLLMProvider()

    if config.provider == "openai":
        return OpenAILLMProvider(
            model=config.model,
            temperature=config.temperature,
        )

    if config.provider == "claude":
        return ClaudeProvider(
            model=config.model,
            temperature=config.temperature,
        )

    raise ValueError(f"Provider '{config.provider}' is not supported yet.")


def get_provider_metadata(provider):
    """Return provider metadata when the provider supports the LLM contract."""
    if not hasattr(provider, "metadata"):
        return None

    return provider.metadata()
