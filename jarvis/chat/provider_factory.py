from jarvis.llm import LLMProviderFactory


class ProviderFactory:
    """Backward-compatible factory for LLM providers."""

    def __init__(self, diagnostics_collector=None):
        """Create a provider factory."""
        self.llm_factory = LLMProviderFactory(diagnostics_collector=diagnostics_collector)

    def create(self, config, diagnostics_collector=None):
        """Return an LLM provider for the configured provider name."""
        if diagnostics_collector is not None:
            self.llm_factory = LLMProviderFactory(diagnostics_collector=diagnostics_collector)

        return self.llm_factory.create(config)
