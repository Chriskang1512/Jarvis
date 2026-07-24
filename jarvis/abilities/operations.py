from dataclasses import dataclass, field


READ_OPERATIONS = {"get", "list", "query", "recall", "search"}
WRITE_OPERATIONS = {
    "cancel",
    "complete",
    "create",
    "delete",
    "forget",
    "remember",
    "reply",
    "restore",
    "send",
    "update",
}

DEFAULT_ABILITY_OPERATIONS = {
    "calendar": ("list", "create", "update", "delete"),
    "contacts": ("list", "get", "create", "update", "delete"),
    "mail": ("list", "search", "get", "send", "reply"),
    "memory": ("list", "recall", "remember", "forget"),
    "reminder": ("list", "create", "update", "cancel", "delete"),
    "todo": ("list", "create", "update", "complete", "delete", "restore"),
    "weather": ("query",),
}


@dataclass(frozen=True)
class CapabilityOperationMetadata:
    """Execution contract for one Registry capability operation."""

    capability: str
    operation: str
    input_schema: dict = field(default_factory=dict)
    output_schema: object = field(default_factory=dict)
    permission: str = "safe"
    contract_version: str = "1.0"
    lifecycle: str = "stable"
    side_effect: str = "none"
    input_schema_version: str = "1.0"
    output_schema_version: str = "1.0"
    parallel_safe: bool = False
    deduplicatable: bool = False
    required_predecessors: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "required_predecessors", tuple(self.required_predecessors))

    @property
    def id(self):
        return f"{self.capability}.{self.operation}"


def derive_operation_metadata(ability):
    """Create compatibility operation contracts for existing Abilities."""
    metadata = ability.metadata
    operations = DEFAULT_ABILITY_OPERATIONS.get(metadata.id, ())
    return tuple(
        CapabilityOperationMetadata(
            capability=metadata.id,
            operation=operation,
            input_schema=dict(metadata.input_schema) if isinstance(metadata.input_schema, dict) else {},
            output_schema=metadata.output_schema,
            permission="confirm_required" if operation in WRITE_OPERATIONS else "safe",
            side_effect="external_write" if operation in WRITE_OPERATIONS else "none",
            parallel_safe=operation in READ_OPERATIONS,
            deduplicatable=operation in READ_OPERATIONS,
        )
        for operation in operations
    )
