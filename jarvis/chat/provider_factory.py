from jarvis.chat.providers import MockChatProvider, OpenAIProvider


class ProviderFactory:
    """Create ChatProvider instances from JarvisConfig."""

    def create(self, config):
        """Return a provider for the configured provider name."""
        if config.provider == "mock":
            return MockChatProvider()

        if config.provider == "openai":
            return OpenAIProvider(
                model=config.model,
                temperature=config.temperature,
            )

        raise ValueError(f"Provider '{config.provider}' is not supported yet.")
