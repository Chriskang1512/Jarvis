from typing import Protocol

from jarvis.capabilities.metadata import CapabilityMetadata


class Capability(Protocol):
    """Common contract for Jarvis capability plugins."""

    metadata: CapabilityMetadata

    def get_tools(self):
        """Return tools exposed by this capability."""
        ...
