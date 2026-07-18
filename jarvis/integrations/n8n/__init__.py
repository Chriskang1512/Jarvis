"""n8n integration bridge provider."""

from jarvis.integrations.n8n.provider import MockIntegrationBridge, N8nBridgeProvider, create_integration_bridge
from jarvis.integrations.n8n.registry import WorkflowRegistry

__all__ = [
    "MockIntegrationBridge",
    "N8nBridgeProvider",
    "WorkflowRegistry",
    "create_integration_bridge",
]
