class CapabilityRegistry:
    """Store and register capability plugins."""

    def __init__(self):
        """Create an empty capability registry."""
        self.capabilities = {}

    def register(self, capability):
        """Register one capability by metadata ID."""
        capability_id = capability.metadata.id

        if capability_id in self.capabilities:
            raise ValueError(f"Capability '{capability_id}' is already registered.")

        self.capabilities[capability_id] = capability

    def get(self, capability_id):
        """Return one capability by ID."""
        return self.capabilities.get(capability_id)

    def exists(self, capability_id):
        """Return whether a capability is registered."""
        return capability_id in self.capabilities

    def list(self):
        """Return all capabilities sorted by ID."""
        return [
            self.capabilities[capability_id]
            for capability_id in sorted(self.capabilities)
        ]

    def list_enabled(self):
        """Return enabled capabilities sorted by ID."""
        return [
            capability
            for capability in self.list()
            if capability.metadata.enabled
        ]

    def enable(self, capability_id):
        """Enable one registered capability."""
        capability = self.get(capability_id)

        if capability is None:
            return False

        capability.metadata.enabled = True
        return True

    def disable(self, capability_id):
        """Disable one registered capability."""
        capability = self.get(capability_id)

        if capability is None:
            return False

        capability.metadata.enabled = False
        return True

    def remove(self, capability_id):
        """Remove one registered capability."""
        if capability_id not in self.capabilities:
            return False

        del self.capabilities[capability_id]
        return True

    def upgrade(self, capability):
        """Replace an existing capability with a newer instance."""
        capability_id = capability.metadata.id

        if capability_id not in self.capabilities:
            raise ValueError(f"Capability '{capability_id}' is not registered.")

        self.capabilities[capability_id] = capability

    def register_tools(self, tool_registry, diagnostics_collector=None):
        """Register enabled capability tools into the shared ToolRegistry."""
        for capability in self.list_enabled():
            for tool in capability.get_tools():
                tool_registry.register(tool)
                log_event(diagnostics_collector, "capability.tool.registered")


def log_event(diagnostics_collector, message):
    """Publish a capability diagnostics event when available."""
    if diagnostics_collector is None:
        return

    diagnostics_collector.log_event(message)
