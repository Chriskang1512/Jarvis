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
    implementation_id: str = ""
    result_equivalence_key: str = ""
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0
    network_required: bool = False
    availability: str = "ONLINE"
    reliability_score: float = 1.0
    health_reason: str = "NONE"

    def __post_init__(self):
        object.__setattr__(self, "required_predecessors", tuple(self.required_predecessors))
        if not self.implementation_id:
            object.__setattr__(self, "implementation_id", f"ability:{self.capability}")
        if not self.result_equivalence_key:
            object.__setattr__(self, "result_equivalence_key", self.id)
        if float(self.estimated_cost) < 0:
            raise ValueError("estimated_cost must not be negative.")
        if int(self.estimated_latency_ms) < 0:
            raise ValueError("estimated_latency_ms must not be negative.")
        availability = str(self.availability or "").upper()
        if availability not in {"ONLINE", "DEGRADED", "OFFLINE"}:
            raise ValueError("availability must be ONLINE, DEGRADED, or OFFLINE.")
        object.__setattr__(self, "availability", availability)
        if not 0.0 <= float(self.reliability_score) <= 1.0:
            raise ValueError("reliability_score must be between 0.0 and 1.0.")
        health_reason = str(self.health_reason or "").upper()
        valid_health_reasons = {
            "NONE",
            "TIMEOUT",
            "RATE_LIMIT",
            "AUTH_FAILURE",
            "NETWORK",
            "SERVER_ERROR",
            "UNKNOWN",
        }
        if health_reason not in valid_health_reasons:
            raise ValueError("Unknown health_reason.")
        if availability == "ONLINE" and health_reason != "NONE":
            raise ValueError("ONLINE operation health_reason must be NONE.")
        if availability != "ONLINE" and health_reason == "NONE":
            health_reason = "UNKNOWN"
        object.__setattr__(self, "health_reason", health_reason)

    @property
    def id(self):
        return f"{self.capability}.{self.operation}"


def derive_operation_metadata(ability):
    """Create compatibility operation contracts for existing Abilities."""
    metadata = ability.metadata
    operations = DEFAULT_ABILITY_OPERATIONS.get(metadata.id, ())
    network_required = bool(getattr(metadata, "provider", ""))
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
            implementation_id=f"ability:{metadata.id}",
            estimated_cost=1.0 if network_required else 0.0,
            estimated_latency_ms=500 if network_required else 5,
            network_required=network_required,
        )
        for operation in operations
    )
