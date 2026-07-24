"""Composable Google provider context."""

from dataclasses import dataclass

from jarvis.providers.google.auth import GoogleAuthManager
from jarvis.providers.google.client_factory import GoogleClientFactory
from jarvis.providers.google.config import GoogleProviderConfig
from jarvis.providers.google.error_mapper import GoogleErrorMapper
from jarvis.providers.google.request_executor import GoogleRequestExecutor


@dataclass(frozen=True)
class GoogleProviderContext:
    """Shared Google provider components without provider-specific logic."""

    config: GoogleProviderConfig
    auth_manager: GoogleAuthManager
    client_factory: GoogleClientFactory
    error_mapper: GoogleErrorMapper
    request_executor: GoogleRequestExecutor

    @classmethod
    def create(cls, config=None, auth_manager=None, client_factory=None, error_mapper=None, request_executor=None):
        """Create a context with default common components."""
        config = config or GoogleProviderConfig()
        auth_manager = auth_manager or GoogleAuthManager(config)
        error_mapper = error_mapper or GoogleErrorMapper()
        client_factory = client_factory or GoogleClientFactory(auth_manager=auth_manager, config=config)
        request_executor = request_executor or GoogleRequestExecutor(error_mapper=error_mapper)
        return cls(
            config=config,
            auth_manager=auth_manager,
            client_factory=client_factory,
            error_mapper=error_mapper,
            request_executor=request_executor,
        )
