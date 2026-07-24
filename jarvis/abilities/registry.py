from dataclasses import replace

from jarvis.abilities.adapter import AbilityToolAdapter
from jarvis.abilities.operations import derive_operation_metadata


class AbilityRegistry:
    """Store abilities and expose them as ToolRouter-compatible tools."""

    def __init__(self):
        """Create an empty ability registry."""
        self.abilities = {}
        self.capability_index = {}
        self.operation_index = {}
        self.operation_candidates = {}

    def register(self, ability):
        """Register one ability by metadata ID."""
        ability = normalize_ability_metadata(ability)
        name = ability.metadata.id

        if name in self.abilities:
            raise ValueError(f"Ability '{name}' is already registered.")

        self.abilities[name] = ability
        self.index_capabilities(ability)
        for operation in derive_operation_metadata(ability):
            self.register_operation(operation)

    def get(self, name):
        """Return one ability by name."""
        return self.abilities.get(name)

    def exists(self, name):
        """Return whether an ability is registered."""
        return name in self.abilities

    def list(self):
        """Return all abilities sorted by name."""
        return [
            self.abilities[name]
            for name in sorted(self.abilities)
        ]

    def list_capabilities(self, ability_id=None):
        """Return capabilities known by the registry."""
        if ability_id is None:
            return sorted(self.capability_index)

        ability = self.get(ability_id)

        if ability is None:
            return []

        return list(ability.metadata.capabilities)

    def find_by_capability(self, capability):
        """Return abilities that expose one capability."""
        return [
            self.abilities[ability_id]
            for ability_id in self.capability_index.get(capability, [])
        ]

    def register_operation(self, metadata, replace_existing=False):
        """Register one operation-level execution contract."""
        if metadata.id in self.operation_index and not replace_existing:
            raise ValueError(f"Operation '{metadata.id}' is already registered.")
        self.operation_index[metadata.id] = metadata
        candidates = self.operation_candidates.setdefault(metadata.id, {})
        if replace_existing:
            candidates.pop(metadata.implementation_id, None)
        candidates[metadata.implementation_id] = metadata

    def register_operation_candidate(self, metadata):
        """Register an equivalent implementation candidate for one operation."""
        candidates = self.operation_candidates.setdefault(metadata.id, {})
        if metadata.implementation_id in candidates:
            raise ValueError(
                f"Operation candidate '{metadata.id}:{metadata.implementation_id}' is already registered."
            )
        candidates[metadata.implementation_id] = metadata

    def list_operation_candidates(self, capability, operation=""):
        """Return deterministic implementation candidates for an operation."""
        operation_id = capability if not operation else f"{capability}.{operation}"
        return [
            self.operation_candidates[operation_id][key]
            for key in sorted(self.operation_candidates.get(operation_id, {}))
        ]

    def get_operation(self, capability, operation=""):
        """Return operation metadata by separate or combined identifier."""
        operation_id = capability if not operation else f"{capability}.{operation}"
        return self.operation_index.get(operation_id)

    def list_operations(self, capability=None):
        """Return normalized operation contracts."""
        operations = [self.operation_index[key] for key in sorted(self.operation_index)]
        if capability is None:
            return operations
        return [item for item in operations if item.capability == capability]

    def index_capabilities(self, ability):
        """Record capability-to-ability mappings for intent parsing."""
        ability_id = ability.metadata.id

        for capability in ability.metadata.capabilities:
            self.capability_index.setdefault(capability, [])

            if ability_id not in self.capability_index[capability]:
                self.capability_index[capability].append(ability_id)

    def register_tools(self, tool_registry):
        """Register all abilities into the shared ToolRegistry as adapters."""
        for ability in self.list():
            tool_registry.register(AbilityToolAdapter(ability))


def normalize_ability_metadata(ability):
    """Fill common metadata from ability/provider defaults."""
    provider = getattr(ability.metadata, "provider", "")

    if provider == "":
        ability_provider = getattr(ability, "provider", None)
        provider = getattr(ability_provider, "provider_name", "")

    priority = getattr(ability.metadata, "priority", "normal") or "normal"

    if provider != getattr(ability.metadata, "provider", "") or priority != getattr(ability.metadata, "priority", "normal"):
        ability.metadata = replace(ability.metadata, provider=provider, priority=priority)

    return ability
