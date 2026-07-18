from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationProviderCapabilities:
    """Describe what an integration provider can do."""

    health: bool = True
    execute: bool = True
    supports_confirmation: bool = False
    supports_stream: bool = False
    supports_async: bool = False
