from jarvis.capabilities.metadata import CapabilityMetadata


class LifeCapability:
    """Capability skeleton for personal life workflows."""

    metadata = CapabilityMetadata(
        id="life",
        name="Life",
        description="Personal life assistant capability.",
        version="0.1.0",
        tools=[],
    )

    def get_tools(self):
        """Return tools owned by this capability."""
        return []


def create_capability():
    """Create the Life capability."""
    return LifeCapability()
