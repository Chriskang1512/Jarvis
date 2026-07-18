from typing import Protocol

from jarvis.integrations.bridge.health import IntegrationHealth
from jarvis.integrations.bridge.request import IntegrationRequest
from jarvis.integrations.bridge.result import IntegrationResult


class IntegrationBridge(Protocol):
    """Common boundary for external automation providers."""

    def health(self) -> IntegrationHealth:
        """Return bridge health without executing a workflow."""
        ...

    def execute(self, request: IntegrationRequest) -> IntegrationResult:
        """Execute one registered workflow request."""
        ...
