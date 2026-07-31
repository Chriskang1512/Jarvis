"""Contracts for capability-aware planning without execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from jarvis.goals import GoalSpecification, SemanticContext
from jarvis.native_task_graph import (
    BindingSourceType,
    ExecutionMode,
    NativeTaskGraph,
    PermissionRequirement,
    ValidationReport,
    VerificationLevel,
)


def utc_now():
    return datetime.now(timezone.utc)


class Availability(str, Enum):
    AVAILABLE = "Available"
    DEGRADED = "Degraded"
    UNAVAILABLE = "Unavailable"


class PlannerStatus(str, Enum):
    PLANNED = "Planned"
    NEEDS_USER_INPUT = "NeedsUserInput"
    UNSUPPORTED = "Unsupported"
    INVALID = "Invalid"
    FAILED = "Failed"


class PlannerType(str, Enum):
    RULE = "RulePlanner"
    AI = "AIPlanner"
    HYBRID = "HybridPlanner"


class PlannerFailureReason(str, Enum):
    UNSUPPORTED_CAPABILITY = "UnsupportedCapability"
    UNSUPPORTED_CONDITIONAL = "UnsupportedConditional"
    POLICY_BLOCKED = "PolicyBlocked"
    VALIDATION_FAILED = "ValidationFailed"
    PLANNER_FAILED = "PlannerFailed"


@dataclass(frozen=True)
class PlannerFailure:
    reason: PlannerFailureReason
    missing_capabilities: tuple[str, ...] = ()
    missing_nodes: tuple[str, ...] = ()
    suggested_capabilities: tuple[str, ...] = ()
    recoverable: bool = False

    def __post_init__(self):
        object.__setattr__(
            self, "missing_capabilities", tuple(self.missing_capabilities)
        )
        object.__setattr__(self, "missing_nodes", tuple(self.missing_nodes))
        object.__setattr__(
            self, "suggested_capabilities", tuple(self.suggested_capabilities)
        )


@dataclass(frozen=True)
class CapabilityInputDefinition:
    name: str
    value_type: str
    is_required: bool = False
    description: str = ""
    default_value: Any = None
    allowed_sources: tuple[BindingSourceType, ...] = ()
    constraints: Mapping[str, Any] = field(default_factory=dict)
    is_sensitive: bool = False

    def __post_init__(self):
        if not self.name or not self.value_type:
            raise ValueError("Capability input name and value_type are required.")
        object.__setattr__(self, "allowed_sources", tuple(self.allowed_sources))
        object.__setattr__(
            self, "constraints", MappingProxyType(dict(self.constraints))
        )


@dataclass(frozen=True)
class CapabilityOutputDefinition:
    name: str
    value_type: str
    description: str = ""
    is_required: bool = True
    artifact_type: str = ""
    is_sensitive: bool = False

    def __post_init__(self):
        if not self.name or not self.value_type:
            raise ValueError("Capability output name and value_type are required.")


@dataclass(frozen=True)
class ExecutionCharacteristics:
    side_effect: str = "none"
    network_required: bool = False
    parallel_safe: bool = False
    estimated_latency_ms: int = 0


@dataclass(frozen=True)
class VerificationSupport:
    levels: tuple[VerificationLevel, ...] = (VerificationLevel.SCHEMA,)
    read_back_capability_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "levels", tuple(self.levels))


@dataclass(frozen=True)
class ProviderRequirements:
    network_required: bool = False
    required_features: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "required_features", tuple(self.required_features))


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    version: str
    display_name: str
    description: str
    domain: str
    operation: str
    input_schema: tuple[CapabilityInputDefinition, ...] = ()
    output_schema: tuple[CapabilityOutputDefinition, ...] = ()
    permission_requirement: PermissionRequirement = PermissionRequirement.SAFE
    execution_characteristics: ExecutionCharacteristics = field(
        default_factory=ExecutionCharacteristics
    )
    verification_support: VerificationSupport = field(
        default_factory=VerificationSupport
    )
    provider_requirements: ProviderRequirements = field(
        default_factory=ProviderRequirements
    )
    tags: tuple[str, ...] = ()
    availability: Availability = Availability.AVAILABLE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.capability_id or "." not in self.capability_id:
            raise ValueError("CapabilityId must be a stable domain.operation id.")
        provider_prefixes = ("google_", "google.", "gmail.", "outlook.", "openweather.")
        if self.capability_id.lower().startswith(provider_prefixes):
            raise ValueError("CapabilityId cannot include a provider name.")
        if self.capability_id != f"{self.domain}.{self.operation}":
            raise ValueError("CapabilityId must equal domain.operation.")
        object.__setattr__(self, "input_schema", tuple(self.input_schema))
        object.__setattr__(self, "output_schema", tuple(self.output_schema))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def input(self, name):
        return next((item for item in self.input_schema if item.name == name), None)

    def output(self, name):
        return next((item for item in self.output_schema if item.name == name), None)


@dataclass(frozen=True)
class DisabledCapability:
    capability_id: str
    reason: str


@dataclass(frozen=True)
class CapabilityRegistrySnapshot:
    snapshot_id: str
    created_at: datetime
    schema_version: str
    capabilities: tuple[CapabilityDescriptor, ...]
    environment_constraints: Mapping[str, Any] = field(default_factory=dict)
    disabled_capabilities: tuple[DisabledCapability, ...] = ()
    registry_hash: str = ""

    def __post_init__(self):
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(
            self,
            "environment_constraints",
            MappingProxyType(dict(self.environment_constraints)),
        )
        object.__setattr__(
            self, "disabled_capabilities", tuple(self.disabled_capabilities)
        )
        calculated = calculate_registry_hash(self.capabilities)
        if self.registry_hash and self.registry_hash != calculated:
            raise ValueError("RegistryHash does not match snapshot capabilities.")
        object.__setattr__(self, "registry_hash", calculated)

    @classmethod
    def create(
        cls,
        capabilities,
        *,
        environment_constraints=None,
        disabled_capabilities=(),
        snapshot_id="",
        created_at=None,
    ):
        available = tuple(
            item
            for item in capabilities
            if item.availability != Availability.UNAVAILABLE
        )
        return cls(
            snapshot_id=snapshot_id or f"snapshot-{uuid4()}",
            created_at=created_at or utc_now(),
            schema_version="1.0",
            capabilities=available,
            environment_constraints=environment_constraints or {},
            disabled_capabilities=tuple(disabled_capabilities),
        )

    def get(self, capability_id):
        return next(
            (
                item
                for item in self.capabilities
                if item.capability_id == capability_id
            ),
            None,
        )


@dataclass(frozen=True)
class PlanningPolicy:
    version: str = "1.0"
    max_nodes: int = 8
    allow_conditions: bool = True
    allow_transforms: bool = True
    allow_user_confirmation: bool = True
    allow_external_mutation: bool = True
    allow_previous_result: bool = True
    preferred_execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    planner_timeout_seconds: float = 8.0
    max_repair_attempts: int = 2


@dataclass(frozen=True)
class PlannerRequest:
    goal: GoalSpecification
    semantic_context: SemanticContext
    capability_snapshot: CapabilityRegistrySnapshot
    planning_policy: PlanningPolicy = field(default_factory=PlanningPolicy)
    previous_validation_report: ValidationReport | None = None
    existing_graph: NativeTaskGraph | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class Assumption:
    field: str
    assumed_value: Any
    reason: str
    confidence: float
    source: str


@dataclass(frozen=True)
class MissingInput:
    capability_id: str
    field: str
    reason: str
    is_sensitive: bool = False


@dataclass(frozen=True)
class SuccessCriterionMapping:
    criterion_id: str
    node_id: str
    output_key: str
    verification_level: VerificationLevel


@dataclass(frozen=True)
class PlannerDiagnostics:
    planner_type: str
    planner_duration_ms: int = 0
    selected_capabilities: tuple[str, ...] = ()
    rejected_capabilities: tuple[str, ...] = ()
    repair_count: int = 0
    validation_issues: tuple[str, ...] = ()
    capability_snapshot_id: str = ""
    registry_hash: str = ""
    routing_reason: str = ""
    confidence: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    ai_failure: str = ""
    input_length: int = 0
    input_hash: str = ""
    entity_summary: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self):
        object.__setattr__(
            self,
            "entity_summary",
            tuple(
                MappingProxyType(dict(item))
                for item in self.entity_summary
            ),
        )


@dataclass(frozen=True)
class PlannerResult:
    status: PlannerStatus
    graph: NativeTaskGraph | None
    planner_type: PlannerType
    model_id: str
    capability_snapshot_id: str
    confidence: float
    assumptions: tuple[Assumption, ...] = ()
    missing_inputs: tuple[MissingInput, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: PlannerDiagnostics | None = None
    success_criteria_mappings: tuple[SuccessCriterionMapping, ...] = ()
    failure: PlannerFailure | None = None
    created_at: datetime = field(default_factory=utc_now)


def calculate_registry_hash(capabilities):
    payload = [
        capability_to_dict(item)
        for item in sorted(capabilities, key=lambda value: value.capability_id)
    ]
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def capability_to_dict(item):
    return {
        "capabilityId": item.capability_id,
        "version": item.version,
        "displayName": item.display_name,
        "description": item.description,
        "domain": item.domain,
        "operation": item.operation,
        "inputSchema": [
            {
                "name": value.name,
                "valueType": value.value_type,
                "isRequired": value.is_required,
                "description": value.description,
                "defaultValue": value.default_value,
                "allowedSources": [source.value for source in value.allowed_sources],
                "constraints": dict(value.constraints),
                "isSensitive": value.is_sensitive,
            }
            for value in item.input_schema
        ],
        "outputSchema": [
            {
                "name": value.name,
                "valueType": value.value_type,
                "description": value.description,
                "isRequired": value.is_required,
                "artifactType": value.artifact_type,
                "isSensitive": value.is_sensitive,
            }
            for value in item.output_schema
        ],
        "permissionRequirement": item.permission_requirement.value,
        "executionCharacteristics": {
            "sideEffect": item.execution_characteristics.side_effect,
            "networkRequired": item.execution_characteristics.network_required,
            "parallelSafe": item.execution_characteristics.parallel_safe,
            "estimatedLatencyMs": item.execution_characteristics.estimated_latency_ms,
        },
        "verificationSupport": {
            "levels": [level.value for level in item.verification_support.levels],
            "readBackCapabilityId": item.verification_support.read_back_capability_id,
        },
        "providerRequirements": {
            "networkRequired": item.provider_requirements.network_required,
            "requiredFeatures": list(
                item.provider_requirements.required_features
            ),
        },
        "tags": list(item.tags),
        "availability": item.availability.value,
        "metadata": dict(item.metadata),
    }
