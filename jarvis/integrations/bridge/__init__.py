"""Common integration bridge contracts."""

from jarvis.integrations.bridge.base import IntegrationBridge
from jarvis.integrations.bridge.capabilities import IntegrationProviderCapabilities
from jarvis.integrations.bridge.health import IntegrationHealth
from jarvis.integrations.bridge.metrics import IntegrationMetrics
from jarvis.integrations.bridge.request import IntegrationRequest
from jarvis.integrations.bridge.result import IntegrationResult

__all__ = [
    "IntegrationBridge",
    "IntegrationProviderCapabilities",
    "IntegrationHealth",
    "IntegrationMetrics",
    "IntegrationRequest",
    "IntegrationResult",
]
