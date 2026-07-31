"""Immutable plan-definition models for Jarvis Native TaskGraph v1.4."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def deep_freeze(value):
    """Recursively freeze JSON-like domain values."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    return value


def mutable_projection(value):
    """Return a JSON-compatible projection of a frozen domain value."""
    if isinstance(value, Mapping):
        return {
            key: mutable_projection(item)
            for key, item in value.items()
        }
    if isinstance(value, (set, frozenset)):
        return [
            mutable_projection(item)
            for item in sorted(value, key=repr)
        ]
    if isinstance(value, (tuple, list)):
        return [mutable_projection(item) for item in value]
    return value


class StringEnum(str, Enum):
    pass


class NodeType(StringEnum):
    CAPABILITY = "Capability"
    CONDITION = "Condition"
    TRANSFORM = "Transform"
    USER_CONFIRMATION = "UserConfirmation"
    RESULT = "Result"
    NO_OP = "NoOp"


class EdgeType(StringEnum):
    DEPENDENCY = "Dependency"
    DATA = "Data"
    CONDITIONAL_TRUE = "ConditionalTrue"
    CONDITIONAL_FALSE = "ConditionalFalse"
    CONTROL = "Control"


class BindingSourceType(StringEnum):
    LITERAL = "Literal"
    GOAL_INPUT = "GoalInput"
    CONTEXT_SLOT = "ContextSlot"
    ENTITY_REFERENCE = "EntityReference"
    NODE_OUTPUT = "NodeOutput"
    PREVIOUS_RESULT = "PreviousResult"
    USER_PREFERENCE = "UserPreference"
    ARTIFACT_REFERENCE = "ArtifactReference"
    SYSTEM_VALUE = "SystemValue"


class PermissionRequirement(StringEnum):
    SAFE = "Safe"
    CONFIRM_REQUIRED = "ConfirmRequired"
    RESTRICTED = "Restricted"


class BackoffStrategy(StringEnum):
    NONE = "None"
    FIXED = "Fixed"
    LINEAR = "Linear"
    EXPONENTIAL = "Exponential"


class VerificationLevel(StringEnum):
    NONE = "None"
    SCHEMA = "Schema"
    SEMANTIC = "Semantic"
    EXTERNAL_READ_BACK = "ExternalReadBack"
    USER_CONFIRMATION = "UserConfirmation"


class FailureAction(StringEnum):
    FAIL_GRAPH = "FailGraph"
    SKIP_NODE = "SkipNode"
    REQUEST_USER_INPUT = "RequestUserInput"
    REPLAN = "Replan"
    USE_FALLBACK = "UseFallback"


class ExecutionMode(StringEnum):
    SEQUENTIAL = "Sequential"
    PARALLEL = "Parallel"


class PermissionStrategy(StringEnum):
    BATCH = "Batch"
    PER_NODE = "PerNode"


class RetentionPolicy(StringEnum):
    TRANSIENT = "Transient"
    SESSION = "Session"
    CONVERSATION = "Conversation"
    PERSISTENT = "Persistent"


class ArtifactPolicy(StringEnum):
    NONE = "None"
    REFERENCE = "Reference"
    PERSIST = "Persist"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    delay_seconds: float = 0.0
    max_delay_seconds: float = 10.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.NONE
    retryable_error_codes: tuple[str, ...] = ()
    retryable_categories: tuple[str, ...] = ()
    jitter: bool = False
    provider_fallback_allowed: bool = False

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be at least 1.")
        if self.delay_seconds < 0:
            raise ValueError("RetryPolicy.delay_seconds cannot be negative.")
        if self.max_delay_seconds < self.delay_seconds:
            raise ValueError(
                "RetryPolicy.max_delay_seconds cannot be less than delay_seconds."
            )
        object.__setattr__(self, "retryable_error_codes", tuple(self.retryable_error_codes))
        object.__setattr__(
            self, "retryable_categories", tuple(self.retryable_categories)
        )


@dataclass(frozen=True)
class VerificationPolicy:
    verification_level: VerificationLevel = VerificationLevel.NONE
    required_evidence: tuple[str, ...] = ()
    minimum_confidence: float = 0.0
    read_back_capability_id: str = ""

    def __post_init__(self):
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1.")
        object.__setattr__(self, "required_evidence", tuple(self.required_evidence))
        if (
            self.verification_level == VerificationLevel.EXTERNAL_READ_BACK
            and not self.read_back_capability_id
        ):
            raise ValueError("ExternalReadBack requires read_back_capability_id.")


@dataclass(frozen=True)
class FailurePolicy:
    action: FailureAction = FailureAction.FAIL_GRAPH
    fallback_capability_id: str = ""

    def __post_init__(self):
        if self.action == FailureAction.USE_FALLBACK and not self.fallback_capability_id:
            raise ValueError("UseFallback requires fallback_capability_id.")


@dataclass(frozen=True)
class GraphExecutionPolicy:
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_node_count: int = 50
    max_execution_duration_seconds: float = 300.0
    allow_parallel_execution: bool = False
    allow_replan: bool = False
    allow_partial_completion: bool = False
    stop_on_failure: bool = True
    permission_strategy: PermissionStrategy = PermissionStrategy.BATCH

    def __post_init__(self):
        if self.max_node_count < 1:
            raise ValueError("max_node_count must be at least 1.")
        if self.max_execution_duration_seconds <= 0:
            raise ValueError("max_execution_duration_seconds must be positive.")
        if self.execution_mode == ExecutionMode.PARALLEL and not self.allow_parallel_execution:
            raise ValueError("Parallel mode requires allow_parallel_execution.")


@dataclass(frozen=True)
class InputBinding:
    source_type: BindingSourceType
    source_node_id: str = ""
    source_key: str = ""
    value: Any = None
    expected_type: str = "Any"
    is_required: bool = True
    default_value: Any = None
    transformation: str = ""

    def __post_init__(self):
        object.__setattr__(self, "value", deep_freeze(self.value))
        object.__setattr__(
            self, "default_value", deep_freeze(self.default_value)
        )
        if not self.expected_type:
            raise ValueError("InputBinding.expected_type is required.")
        if self.source_type == BindingSourceType.LITERAL:
            if self.source_node_id or self.source_key:
                raise ValueError("Literal binding cannot reference a source node or key.")
        elif self.source_type == BindingSourceType.NODE_OUTPUT:
            if not self.source_node_id or not self.source_key:
                raise ValueError("NodeOutput binding requires source_node_id and source_key.")
        else:
            if self.source_node_id:
                raise ValueError(
                    f"{self.source_type.value} binding cannot reference source_node_id."
                )
            if not self.source_key:
                raise ValueError(f"{self.source_type.value} binding requires source_key.")


@dataclass(frozen=True)
class OutputDefinition:
    output_key: str
    value_type: str
    is_required: bool = True
    artifact_type: str = ""
    description: str = ""
    retention_policy: RetentionPolicy = RetentionPolicy.TRANSIENT

    def __post_init__(self):
        if not self.output_key or not self.value_type:
            raise ValueError("OutputDefinition output_key and value_type are required.")


@dataclass(frozen=True)
class TaskNode:
    node_id: str
    node_type: NodeType
    capability_id: str
    operation: str
    display_name: str = ""
    description: str = ""
    inputs: Mapping[str, InputBinding] = field(default_factory=dict)
    outputs: Mapping[str, OutputDefinition] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    permission_requirement: PermissionRequirement = PermissionRequirement.SAFE
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    verification_policy: VerificationPolicy = field(default_factory=VerificationPolicy)
    failure_policy: FailurePolicy = field(default_factory=FailurePolicy)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.node_id:
            raise ValueError("TaskNode.node_id is required.")
        if self.node_type == NodeType.CAPABILITY and (
            not self.capability_id or not self.operation
        ):
            raise ValueError("Capability nodes require capability_id and operation.")
        inputs = dict(self.inputs)
        outputs = dict(self.outputs)
        if any(key != value.output_key for key, value in outputs.items()):
            raise ValueError("Output map key must match OutputDefinition.output_key.")
        object.__setattr__(self, "inputs", MappingProxyType(inputs))
        object.__setattr__(self, "outputs", MappingProxyType(outputs))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "required_inputs", tuple(self.required_inputs))
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))


@dataclass(frozen=True)
class TaskEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType = EdgeType.DEPENDENCY
    condition: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.edge_id or not self.source_node_id or not self.target_node_id:
            raise ValueError("TaskEdge ids and node references are required.")
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))


@dataclass(frozen=True)
class GraphOutput:
    output_id: str
    source_node_id: str
    source_output_key: str
    output_type: str
    display_name: str = ""
    is_primary: bool = False
    artifact_policy: ArtifactPolicy = ArtifactPolicy.NONE

    def __post_init__(self):
        if not all(
            (self.output_id, self.source_node_id, self.source_output_key, self.output_type)
        ):
            raise ValueError("GraphOutput identifiers and output_type are required.")


@dataclass(frozen=True)
class NativeTaskGraph:
    graph_id: str
    goal_id: str
    conversation_id: str
    version: int = 1
    nodes: tuple[TaskNode, ...] = ()
    edges: tuple[TaskEdge, ...] = ()
    outputs: tuple[GraphOutput, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    execution_policy: GraphExecutionPolicy = field(default_factory=GraphExecutionPolicy)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    schema_version: str = "1.0"

    def __post_init__(self):
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))
        if self.version < 1:
            raise ValueError("NativeTaskGraph.version must be at least 1.")
        for name in ("created_at", "updated_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware.")
        dependencies = {
            node.node_id: tuple(
                edge.source_node_id
                for edge in self.edges
                if edge.target_node_id == node.node_id
                and edge.edge_type
                in {
                    EdgeType.DEPENDENCY,
                    EdgeType.DATA,
                    EdgeType.CONTROL,
                    EdgeType.CONDITIONAL_TRUE,
                    EdgeType.CONDITIONAL_FALSE,
                }
            )
            for node in self.nodes
        }
        object.__setattr__(
            self,
            "nodes",
            tuple(
                replace(node, dependencies=dependencies[node.node_id])
                for node in self.nodes
            ),
        )

    def node(self, node_id: str) -> TaskNode | None:
        return next((node for node in self.nodes if node.node_id == node_id), None)

    def dependencies_for(self, node_id: str) -> tuple[str, ...]:
        node = self.node(node_id)
        return node.dependencies if node else ()
