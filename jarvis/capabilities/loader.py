import importlib
import pkgutil

from jarvis.capabilities.registry import CapabilityRegistry


SKIPPED_MODULES = {
    "base",
    "loader",
    "metadata",
    "registry",
}


class CapabilityLoader:
    """Discover and load installed capability plugins."""

    def __init__(self, package=None, diagnostics_collector=None, memory_manager=None):
        """Create a loader for one capability package."""
        self.package = package or importlib.import_module("jarvis.capabilities")
        self.diagnostics_collector = diagnostics_collector
        self.memory_manager = memory_manager

    def discover(self):
        """Discover capability factories from the configured package."""
        capabilities = []

        for module_info in pkgutil.iter_modules(
            self.package.__path__,
            prefix=f"{self.package.__name__}.",
        ):
            short_name = module_info.name.rsplit(".", 1)[-1]

            if short_name in SKIPPED_MODULES:
                continue

            module = importlib.import_module(module_info.name)
            factory = getattr(module, "create_capability", None)

            if factory is None:
                continue

            capabilities.append(
                create_capability_from_factory(
                    factory=factory,
                    memory_manager=self.memory_manager,
                )
            )

        return capabilities

    def load(self):
        """Load discovered capabilities into a registry."""
        registry = CapabilityRegistry()

        for capability in self.discover():
            try:
                registry.register(capability)
                self.log_event("capability.loaded")

                if capability.metadata.enabled:
                    self.log_event("capability.enabled")
                else:
                    self.log_event("capability.disabled")
            except Exception:
                self.log_event("capability.failed")

        return registry

    def register_capability_tools(self, capability_registry, tool_registry):
        """Register enabled capability tools into the ToolRegistry."""
        capability_registry.register_tools(
            tool_registry=tool_registry,
            diagnostics_collector=self.diagnostics_collector,
        )

    def log_event(self, message):
        """Publish capability diagnostics event when available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def create_capability_from_factory(factory, memory_manager=None):
    """Create a capability while passing optional runtime dependencies."""
    try:
        return factory(memory_manager=memory_manager)
    except TypeError:
        return factory()
