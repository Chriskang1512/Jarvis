"""Durable TaskGraph foundation for multi-turn agent execution."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
import hashlib
import json
from threading import RLock
from time import perf_counter
from uuid import uuid4

from jarvis.debug_trace import trace_event
from jarvis.runtime.turn_lock import BusyPolicy, TurnOwner, TurnPriority


class InvalidTaskGraph(ValueError):
    pass


class GraphValidationCode(str, Enum):
    EMPTY = "EMPTY"
    DUPLICATE_NODE = "DUPLICATE_NODE"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    CYCLE = "CYCLE"
    MISSING_INPUT = "MISSING_INPUT"
    INVALID_INPUT_BINDING = "INVALID_INPUT_BINDING"
    ABILITY_UNAVAILABLE = "ABILITY_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PERMISSION_CONFIRM_REQUIRED = "PERMISSION_CONFIRM_REQUIRED"


class SemanticValidationCode(str, Enum):
    UNKNOWN_SEMANTIC_TYPE = "UNKNOWN_SEMANTIC_TYPE"
    INPUT_TYPE_MISMATCH = "INPUT_TYPE_MISMATCH"
    OUTPUT_TYPE_MISMATCH = "OUTPUT_TYPE_MISMATCH"
    ABILITY_CONTRACT_MISSING = "ABILITY_CONTRACT_MISSING"
    SEMANTIC_CHECK_FAILED = "SEMANTIC_CHECK_FAILED"


class GraphValidationStage(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    SEMANTIC = "SEMANTIC"
    CAPABILITY = "CAPABILITY"
    PERMISSION = "PERMISSION"


def normalize_semantic_name(value):
    return "".join(
        character
        for character in str(value or "").strip().lower()
        if character.isalnum()
    )


@dataclass(frozen=True)
class SemanticType:
    name: str
    parents: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("SemanticType name cannot be empty.")
        object.__setattr__(self, "parents", tuple(self.parents))
        object.__setattr__(self, "aliases", tuple(self.aliases))


class SemanticRegistry:
    """Canonical registry for graph and Ability semantic data types."""

    def __init__(self, semantic_types=()):
        self._types = {}
        self._aliases = {}
        for semantic_type in semantic_types:
            self.register(semantic_type)

    def register(self, semantic_type):
        semantic_type = (
            semantic_type
            if isinstance(semantic_type, SemanticType)
            else SemanticType(**semantic_type)
        )
        key = normalize_semantic_name(semantic_type.name)
        if key in self._types:
            raise ValueError(f"Semantic type is already registered: {semantic_type.name}")
        self._types[key] = semantic_type
        for alias in (semantic_type.name, *semantic_type.aliases):
            alias_key = normalize_semantic_name(alias)
            existing = self._aliases.get(alias_key)
            if existing is not None and existing != key:
                raise ValueError(f"Semantic type alias is already registered: {alias}")
            self._aliases[alias_key] = key
        return semantic_type

    def resolve(self, name):
        key = self._aliases.get(normalize_semantic_name(name))
        return self._types.get(key) if key else None

    def exists(self, name):
        return self.resolve(name) is not None

    def canonical_name(self, name):
        item = self.resolve(name)
        return item.name if item else ""

    def compatible(self, actual, expected):
        actual_type = self.resolve(actual)
        expected_type = self.resolve(expected)
        if actual_type is None or expected_type is None:
            return False
        if normalize_semantic_name(expected_type.name) == "any":
            return True
        return self._is_a(actual_type.name, expected_type.name, set())

    def _is_a(self, actual, expected, visited):
        actual_key = normalize_semantic_name(actual)
        expected_key = normalize_semantic_name(expected)
        if actual_key == expected_key:
            return True
        if actual_key in visited:
            return False
        visited.add(actual_key)
        item = self.resolve(actual)
        return bool(
            item
            and any(self._is_a(parent, expected, visited) for parent in item.parents)
        )

    def list(self):
        return tuple(self._types[key] for key in sorted(self._types))

    def to_tree(self):
        children = {item.name: [] for item in self.list()}
        roots = []
        for item in self.list():
            known_parents = [
                self.canonical_name(parent)
                for parent in item.parents
                if self.exists(parent)
            ]
            if known_parents:
                for parent in known_parents:
                    children[parent].append(item.name)
            else:
                roots.append(item.name)

        def branch(name, visited):
            if name in visited:
                return {"name": name, "children": []}
            return {
                "name": name,
                "children": [
                    branch(child, visited | {name})
                    for child in sorted(children.get(name, ()))
                ],
            }

        return [branch(name, set()) for name in sorted(roots)]


def create_default_semantic_registry():
    return SemanticRegistry(
        (
            SemanticType("Any"),
            SemanticType("Text", parents=("Any",)),
            SemanticType("Summary", parents=("Text",)),
            SemanticType("WeatherReport", parents=("Text",)),
            SemanticType("HotelRecord", parents=("Any",)),
            SemanticType("HotelList", parents=("Any",)),
            SemanticType("CalendarEvent", parents=("Any",)),
            SemanticType("EmailDraft", parents=("Text",)),
            SemanticType("Image", parents=("Any",)),
            SemanticType("PDF", parents=("Any",), aliases=("application/pdf",)),
            SemanticType("TaskPlan", parents=("Any",)),
            SemanticType("TranslatedText", parents=("Text",)),
        )
    )


DEFAULT_SEMANTIC_REGISTRY = create_default_semantic_registry()


class GraphState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NodeState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    RETRYING = "RETRYING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class TurnResultStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    TIMEOUT = "TIMEOUT"
    WAIT_CONFIRM = "WAIT_CONFIRM"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative.")


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    uri: str = ""
    fingerprint: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "uri": self.uri,
            "fingerprint": self.fingerprint,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class InputBinding:
    """Map an upstream node output or InputEnvelope into a node input."""

    input_name: str
    source_node_id: str = ""
    output_path: str = ""
    required: bool = True
    envelope_path: str = "content"
    input_id: str = ""
    accepted_sources: tuple[str, ...] = ()
    accepted_modalities: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.input_name:
            raise ValueError("InputBinding input_name cannot be empty.")
        object.__setattr__(self, "accepted_sources", tuple(self.accepted_sources))
        object.__setattr__(self, "accepted_modalities", tuple(self.accepted_modalities))

    @property
    def source_kind(self):
        return "node" if self.source_node_id else "envelope"

    def to_dict(self):
        return {
            "input_name": self.input_name,
            "source_node_id": self.source_node_id,
            "output_path": self.output_path,
            "required": self.required,
            "source_kind": self.source_kind,
            "envelope_path": self.envelope_path,
            "input_id": self.input_id,
            "accepted_sources": list(self.accepted_sources),
            "accepted_modalities": list(self.accepted_modalities),
        }


@dataclass(frozen=True)
class GraphValidationIssue:
    code: object
    message: str
    node_id: str = ""
    blocking: bool = True
    stage: GraphValidationStage | None = None
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.code, (GraphValidationCode, SemanticValidationCode)):
            try:
                object.__setattr__(self, "code", GraphValidationCode(self.code))
            except ValueError:
                object.__setattr__(self, "code", SemanticValidationCode(self.code))
        if self.stage is not None:
            object.__setattr__(self, "stage", GraphValidationStage(self.stage))
        object.__setattr__(self, "details", dict(self.details))

    def to_dict(self):
        return {
            "code": self.code.value,
            "message": self.message,
            "node_id": self.node_id,
            "blocking": self.blocking,
            "stage": self.stage.value if self.stage else "",
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class GraphValidationReport:
    graph_id: str
    issues: tuple[GraphValidationIssue, ...] = ()
    stage_durations_ms: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(
            self,
            "stage_durations_ms",
            {
                enum_value(key): round(float(value), 3)
                for key, value in dict(self.stage_durations_ms).items()
            },
        )

    @property
    def valid(self):
        return not any(issue.blocking for issue in self.issues)

    def raise_for_errors(self):
        if not self.valid:
            messages = "; ".join(issue.message for issue in self.issues if issue.blocking)
            raise InvalidTaskGraph(f"TaskGraph validation failed: {messages}")
        return self

    def to_dict(self):
        stages = []
        for stage in GraphValidationStage:
            issues = self.for_stage(stage)
            stages.append(
                {
                    "stage": stage.value,
                    "status": "FAIL" if any(item.blocking for item in issues) else "PASS",
                    "duration_ms": self.stage_durations_ms.get(stage.value),
                    "issues": [item.to_dict() for item in issues],
                }
            )
        return {
            "graph_id": self.graph_id,
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "stages": stages,
        }

    def for_stage(self, stage):
        stage = GraphValidationStage(stage)
        return tuple(issue for issue in self.issues if issue.stage is stage)


@dataclass(frozen=True)
class AbilitySemanticContract:
    ability: str
    input_types: dict = field(default_factory=dict)
    output_types: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "input_types", dict(self.input_types))
        object.__setattr__(self, "output_types", dict(self.output_types))


@dataclass(frozen=True)
class TurnResult:
    turn_id: str
    task_id: str
    node_id: str
    status: TurnResultStatus
    output: object = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    memory_refs: tuple[str, ...] = ()
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    provider_metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "status", TurnResultStatus(self.status))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        object.__setattr__(self, "memory_refs", tuple(self.memory_refs))
        object.__setattr__(self, "provider_metadata", dict(self.provider_metadata))

    def to_dict(self):
        return {
            "turn_id": self.turn_id,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "status": self.status.value,
            "output": self.output,
            "artifact_refs": [artifact.to_dict() for artifact in self.artifact_refs],
            "memory_refs": list(self.memory_refs),
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "provider_metadata": dict(self.provider_metadata),
        }


@dataclass(frozen=True)
class TaskNode:
    node_id: str
    ability: str
    operation: str = ""
    dependencies: tuple[str, ...] = ()
    condition: str = ""
    state: NodeState = NodeState.PENDING
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    input: dict = field(default_factory=dict, repr=False)
    input_bindings: tuple[InputBinding, ...] = ()
    required_inputs: tuple[str, ...] = ()
    provider_capability: str = ""
    input_types: dict = field(default_factory=dict)
    output_types: dict = field(default_factory=dict)
    output: object = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    memory_refs: tuple[str, ...] = ()
    turn_ids: tuple[str, ...] = ()
    attempts: int = 0
    last_error: str = ""

    def __post_init__(self):
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "state", NodeState(self.state))
        object.__setattr__(self, "input", dict(self.input))
        object.__setattr__(
            self,
            "input_bindings",
            tuple(
                item if isinstance(item, InputBinding) else InputBinding(**item)
                for item in self.input_bindings
            ),
        )
        object.__setattr__(self, "required_inputs", tuple(self.required_inputs))
        object.__setattr__(self, "input_types", dict(self.input_types))
        object.__setattr__(self, "output_types", dict(self.output_types))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        object.__setattr__(self, "memory_refs", tuple(self.memory_refs))
        object.__setattr__(self, "turn_ids", tuple(self.turn_ids))

    def to_dict(self, include_input=False):
        result = {
            "node_id": self.node_id,
            "ability": self.ability,
            "operation": self.operation,
            "dependencies": list(self.dependencies),
            "condition": self.condition,
            "state": self.state.value,
            "retry_policy": {
                "max_attempts": self.retry_policy.max_attempts,
                "backoff_seconds": self.retry_policy.backoff_seconds,
            },
            "input_bindings": [binding.to_dict() for binding in self.input_bindings],
            "required_inputs": list(self.required_inputs),
            "provider_capability": self.provider_capability,
            "input_types": dict(self.input_types),
            "output_types": dict(self.output_types),
            "output": self.output,
            "artifact_refs": [artifact.to_dict() for artifact in self.artifact_refs],
            "memory_refs": list(self.memory_refs),
            "turn_ids": list(self.turn_ids),
            "attempts": self.attempts,
            "last_error": self.last_error,
        }
        if include_input:
            result["input"] = dict(self.input)
        return result


@dataclass(frozen=True)
class TaskGraph:
    graph_id: str
    task_id: str
    goal: str
    nodes: tuple[TaskNode, ...]
    state: GraphState = GraphState.PENDING
    version: int = 1
    revision: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = now_iso()
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "state", GraphState(self.state))
        if not self.graph_id:
            object.__setattr__(self, "graph_id", f"GRAPH-{uuid4().hex[:10].upper()}")
        if not self.created_at:
            object.__setattr__(self, "created_at", now)
        if not self.updated_at:
            object.__setattr__(self, "updated_at", self.created_at)
        validate_task_graph(self)

    def node(self, node_id):
        for node in self.nodes:
            if node.node_id == str(node_id):
                return node
        raise KeyError(f"Unknown TaskGraph node: {node_id}")

    def ready_nodes(self):
        completed = {
            node.node_id for node in self.nodes if node.state is NodeState.COMPLETED
        }
        return tuple(
            node
            for node in self.nodes
            if node.state in {NodeState.PENDING, NodeState.READY, NodeState.RETRYING}
            and all(dependency in completed for dependency in node.dependencies)
        )

    def to_dict(self, include_inputs=False):
        return {
            "graph_id": self.graph_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "state": self.state.value,
            "version": self.version,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "nodes": [node.to_dict(include_input=include_inputs) for node in self.nodes],
            "edges": [
                {"from": dependency, "to": node.node_id}
                for node in self.nodes
                for dependency in node.dependencies
            ],
        }


@dataclass(frozen=True)
class TaskGraphCheckpoint:
    graph_id: str
    task_id: str
    revision: int
    graph: TaskGraph
    saved_at: str
    fingerprint: str


@dataclass(frozen=True)
class NodeTurnLease:
    graph: TaskGraph
    node_id: str
    turn: object
    input_data: dict = field(default_factory=dict)


class InMemoryTaskGraphCheckpointStore:
    def __init__(self):
        self._items = {}
        self._lock = RLock()

    def save(self, graph):
        checkpoint = TaskGraphCheckpoint(
            graph_id=graph.graph_id,
            task_id=graph.task_id,
            revision=graph.revision,
            graph=graph,
            saved_at=now_iso(),
            fingerprint=task_graph_fingerprint(graph),
        )
        with self._lock:
            self._items[graph.graph_id] = checkpoint
        return checkpoint

    def load(self, graph_id):
        with self._lock:
            return self._items.get(str(graph_id or ""))


class InMemoryTurnResultStore:
    def __init__(self):
        self._items = {}
        self._lock = RLock()

    def save(self, result):
        if not isinstance(result, TurnResult):
            raise TypeError("TurnResultStore accepts TurnResult values.")
        with self._lock:
            self._items[result.turn_id] = result
        return result

    def load(self, turn_id):
        with self._lock:
            return self._items.get(str(turn_id or ""))

    def for_node(self, task_id, node_id):
        with self._lock:
            return tuple(
                result
                for result in self._items.values()
                if result.task_id == str(task_id) and result.node_id == str(node_id)
            )


class TaskGraphCoordinator:
    """Apply graph changes and checkpoint every accepted mutation."""

    def __init__(self, checkpoint_store=None, result_store=None, validator=None):
        self.checkpoint_store = checkpoint_store or InMemoryTaskGraphCheckpointStore()
        self.result_store = result_store or InMemoryTurnResultStore()
        self.validator = validator
        self._lock = RLock()

    def start(self, graph):
        if self.validator is not None:
            report = self.validator.validate(graph)
            trace_event(
                "runtime.task_graph.validated",
                graph_id=graph.graph_id,
                task_id=graph.task_id,
                valid=report.valid,
                issue_count=len(report.issues),
                validation=report.to_dict(),
            )
            report.raise_for_errors()
        return self._save(replace(graph, state=GraphState.RUNNING))

    def refresh_ready(self, graph):
        ready_ids = {node.node_id for node in graph.ready_nodes()}
        nodes = tuple(
            replace(node, state=NodeState.READY)
            if node.node_id in ready_ids and node.state is NodeState.PENDING
            else node
            for node in graph.nodes
        )
        return self._save(replace(graph, nodes=nodes))

    def set_node_state(self, graph, node_id, state):
        node = graph.node(node_id)
        updated_node = replace(node, state=NodeState(state))
        updated = replace_node(graph, updated_node)
        return self._save(replace(updated, state=derive_graph_state(updated)))

    def record_result(self, graph, result):
        result = result if isinstance(result, TurnResult) else TurnResult(**result)
        if result.task_id != graph.task_id:
            raise InvalidTaskGraph("TurnResult task_id does not match TaskGraph.")
        node = graph.node(result.node_id)
        attempts = node.attempts + 1
        if result.status is TurnResultStatus.COMPLETED:
            state = NodeState.COMPLETED
        elif result.status is TurnResultStatus.WAIT_CONFIRM:
            state = NodeState.WAIT_CONFIRM
        elif attempts < node.retry_policy.max_attempts:
            state = NodeState.RETRYING
        else:
            state = NodeState.FAILED
        updated_node = replace(
            node,
            state=state,
            output=result.output,
            artifact_refs=result.artifact_refs,
            memory_refs=result.memory_refs,
            turn_ids=node.turn_ids + (result.turn_id,),
            attempts=attempts,
            last_error=result.error,
        )
        updated = replace_node(graph, updated_node)
        updated = replace(updated, state=derive_graph_state(updated))
        trace_event(
            "runtime.task_graph.node_result",
            graph_id=graph.graph_id,
            task_id=graph.task_id,
            node_id=node.node_id,
            turn_id=result.turn_id,
            node_state=state.value,
            attempts=attempts,
            result_status=result.status.value,
            artifact_count=len(result.artifact_refs),
            memory_ref_count=len(result.memory_refs),
            provider=str(
                result.provider_metadata.get("provider")
                or result.provider_metadata.get("name")
                or ""
            ),
            provider_latency_ms=result.provider_metadata.get(
                "latency_ms",
                result.provider_metadata.get("duration_ms"),
            ),
            output_types=dict(node.output_types),
            dependencies=list(node.dependencies),
        )
        with self._lock:
            self.result_store.save(result)
            return self._save(updated)

    def record_tts(self, graph, status, provider="", latency_ms=None, error=""):
        """Publish a graph-correlated TTS lifecycle observation."""
        normalized = str(getattr(status, "value", status) or "").upper()
        trace_event(
            "runtime.task_graph.tts",
            graph_id=graph.graph_id,
            task_id=graph.task_id,
            status=normalized,
            provider=str(provider or ""),
            latency_ms=latency_ms,
            error=str(error or ""),
        )
        return graph

    def acquire_node_turn(
        self,
        graph,
        node_id,
        turn_lock,
        owner=TurnOwner.PLUGIN,
        policy=BusyPolicy.QUEUE,
        priority=TurnPriority.PLUGIN,
        source="task_graph",
        input_envelopes=(),
        **timeouts,
    ):
        node = graph.node(node_id)
        if node not in graph.ready_nodes() and node.state is not NodeState.READY:
            raise InvalidTaskGraph(f"Node is not ready: {node_id}")
        resolved_input = self.resolve_node_input(
            graph,
            node_id,
            input_envelopes=input_envelopes,
        )
        queued_graph = self.set_node_state(graph, node_id, NodeState.QUEUED)
        try:
            turn = turn_lock.acquire(
                owner,
                policy=policy,
                priority=priority,
                source=source,
                task_id=graph.task_id,
                step_id=node.node_id,
                **timeouts,
            )
        except Exception:
            self.set_node_state(queued_graph, node_id, NodeState.READY)
            raise
        running_graph = self.set_node_state(queued_graph, node_id, NodeState.RUNNING)
        return NodeTurnLease(
            graph=running_graph,
            node_id=node_id,
            turn=turn,
            input_data=resolved_input,
        )

    def resolve_node_input(self, graph, node_id, input_envelopes=()):
        """Materialize static and upstream-bound input for a ready node."""
        node = graph.node(node_id)
        resolved = dict(node.input)
        for binding in node.input_bindings:
            if binding.source_node_id:
                source = graph.node(binding.source_node_id)
                value, found = resolve_output_path(source.output, binding.output_path)
                source_label = (
                    f"{binding.source_node_id}:{binding.output_path or '$'}"
                )
            else:
                envelope = select_input_envelope(input_envelopes, binding)
                value, found = resolve_envelope_path(envelope, binding.envelope_path)
                source_label = f"InputEnvelope:{binding.envelope_path or '$'}"
            if not found:
                if binding.required:
                    raise InvalidTaskGraph(
                        f"Missing input '{binding.input_name}' from "
                        f"{source_label}."
                    )
                continue
            resolved[binding.input_name] = value
        missing = sorted(name for name in node.required_inputs if name not in resolved)
        if missing:
            raise InvalidTaskGraph(
                f"Missing required input for {node.node_id}: {', '.join(missing)}"
            )
        return resolved

    def _save(self, graph):
        with self._lock:
            updated = replace(
                graph,
                revision=graph.revision + 1,
                updated_at=now_iso(),
            )
            self.checkpoint_store.save(updated)
            trace_event(
                "runtime.task_graph.checkpoint",
                graph_id=updated.graph_id,
                task_id=updated.task_id,
                revision=updated.revision,
                state=updated.state.value,
            )
            return updated


def validate_task_graph(graph):
    ids = [node.node_id for node in graph.nodes]
    if not ids:
        raise InvalidTaskGraph("TaskGraph must contain at least one node.")
    if len(ids) != len(set(ids)):
        raise InvalidTaskGraph("TaskGraph node IDs must be unique.")
    known = set(ids)
    for node in graph.nodes:
        if not node.node_id:
            raise InvalidTaskGraph("TaskGraph node ID cannot be empty.")
        if not node.ability:
            raise InvalidTaskGraph(f"TaskGraph node ability cannot be empty: {node.node_id}")
        missing = set(node.dependencies) - known
        if missing:
            raise InvalidTaskGraph(
                f"Unknown dependencies for {node.node_id}: {', '.join(sorted(missing))}"
            )
        if node.node_id in node.dependencies:
            raise InvalidTaskGraph(f"TaskGraph node cannot depend on itself: {node.node_id}")
        for binding in node.input_bindings:
            if not binding.source_node_id:
                continue
            if binding.source_node_id not in known:
                raise InvalidTaskGraph(
                    f"Unknown input source for {node.node_id}: {binding.source_node_id}"
                )
            if binding.source_node_id not in node.dependencies:
                raise InvalidTaskGraph(
                    f"Input source must be a dependency for {node.node_id}: "
                    f"{binding.source_node_id}"
                )
    visiting = set()
    visited = set()

    def visit(node_id):
        if node_id in visiting:
            raise InvalidTaskGraph("TaskGraph must be acyclic.")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in graph.node(node_id).dependencies:
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in ids:
        visit(node_id)
    return graph


class TaskGraphStructuralValidator:
    def validate(self, graph):
        issues = []
        try:
            validate_task_graph(graph)
        except InvalidTaskGraph as error:
            issues.append(
                GraphValidationIssue(
                    code=validation_code_for_error(str(error)),
                    message=str(error),
                    stage=GraphValidationStage.STRUCTURAL,
                )
            )
            return GraphValidationReport(graph.graph_id, tuple(issues))
        for node in graph.nodes:
            bound_names = {binding.input_name for binding in node.input_bindings}
            missing = sorted(
                name
                for name in node.required_inputs
                if name not in node.input and name not in bound_names
            )
            if missing:
                issues.append(
                    GraphValidationIssue(
                        GraphValidationCode.MISSING_INPUT,
                        f"Missing required input declaration for {node.node_id}: "
                        f"{', '.join(missing)}",
                        node.node_id,
                        stage=GraphValidationStage.STRUCTURAL,
                    )
                )
        return GraphValidationReport(graph.graph_id, tuple(issues))


class TaskGraphCapabilityValidator:
    def __init__(self, ability_registry=None, provider_checker=None):
        self.ability_registry = ability_registry
        self.provider_checker = provider_checker

    def validate(self, graph):
        issues = []
        for node in graph.nodes:
            ability = self._ability(node.ability)
            if self.ability_registry is not None and ability is None:
                issues.append(
                    GraphValidationIssue(
                        GraphValidationCode.ABILITY_UNAVAILABLE,
                        f"Ability is unavailable: {node.ability}",
                        node.node_id,
                        stage=GraphValidationStage.CAPABILITY,
                    )
                )
                continue
            if node.provider_capability:
                available = self._provider_available(node, ability)
                if not available:
                    issues.append(
                        GraphValidationIssue(
                            GraphValidationCode.PROVIDER_UNAVAILABLE,
                            f"Provider capability is unavailable: "
                            f"{node.provider_capability}",
                            node.node_id,
                            stage=GraphValidationStage.CAPABILITY,
                        )
                    )
        return GraphValidationReport(graph.graph_id, tuple(issues))

    def _ability(self, ability_id):
        if self.ability_registry is None:
            return None
        getter = getattr(self.ability_registry, "get", None)
        if callable(getter):
            return getter(ability_id)
        return self.ability_registry.get(ability_id)

    def _provider_available(self, node, ability):
        if self.provider_checker is not None:
            return bool(self.provider_checker(node.provider_capability, node, ability))
        registry = self.ability_registry
        if registry is None:
            return False
        get_operation = getattr(registry, "get_operation", None)
        if callable(get_operation) and get_operation(node.provider_capability) is not None:
            return True
        find = getattr(registry, "find_by_capability", None)
        if callable(find) and find(node.provider_capability):
            return True
        metadata = getattr(ability, "metadata", None)
        capabilities = getattr(metadata, "capabilities", ()) if metadata else ()
        return node.provider_capability in capabilities


class TaskGraphPermissionValidator:
    def __init__(self, permission_checker=None, ability_registry=None):
        self.permission_checker = permission_checker
        self.ability_registry = ability_registry

    def validate(self, graph):
        issues = []
        if self.permission_checker is None:
            return GraphValidationReport(graph.graph_id)
        for node in graph.nodes:
            ability = registry_get(self.ability_registry, node.ability)
            if self.permission_checker is not None:
                decision = self.permission_checker(node, ability)
                issue = permission_issue(decision, node.node_id, node.ability)
                if issue is not None:
                    issues.append(replace(issue, stage=GraphValidationStage.PERMISSION))
        return GraphValidationReport(graph.graph_id, tuple(issues))


class TaskGraphValidator:
    """Run ordered preflight stages while preserving the original facade."""

    def __init__(
        self,
        ability_registry=None,
        provider_checker=None,
        permission_checker=None,
        semantic_validator=None,
        structural_validator=None,
        capability_validator=None,
        permission_validator=None,
    ):
        self.validators = (
            structural_validator or TaskGraphStructuralValidator(),
            semantic_validator or TaskGraphSemanticValidator(),
            capability_validator
            or TaskGraphCapabilityValidator(ability_registry, provider_checker),
            permission_validator
            or TaskGraphPermissionValidator(permission_checker, ability_registry),
        )

    def validate(self, graph):
        issues = []
        durations = {}
        for validator in self.validators:
            if validator is None:
                continue
            started = perf_counter()
            report = validator.validate(graph)
            elapsed_ms = (perf_counter() - started) * 1000
            stage = validator_stage(validator)
            if stage is not None:
                durations[stage.value] = round(elapsed_ms, 3)
            issues.extend(report.issues)
        return GraphValidationReport(
            graph.graph_id,
            tuple(issues),
            stage_durations_ms=durations,
        )


def validator_stage(validator):
    stages = (
        (TaskGraphStructuralValidator, GraphValidationStage.STRUCTURAL),
        (TaskGraphSemanticValidator, GraphValidationStage.SEMANTIC),
        (TaskGraphCapabilityValidator, GraphValidationStage.CAPABILITY),
        (TaskGraphPermissionValidator, GraphValidationStage.PERMISSION),
    )
    for validator_type, stage in stages:
        if isinstance(validator, validator_type):
            return stage
    stage = getattr(validator, "stage", None)
    return GraphValidationStage(stage) if stage else None


class TaskGraphSemanticValidator:
    """Check that a structurally valid graph also carries coherent meaning."""

    def __init__(self, contracts=None, semantic_checker=None, registry=None):
        self.contracts = {
            key: (
                value
                if isinstance(value, AbilitySemanticContract)
                else AbilitySemanticContract(ability=key, **value)
            )
            for key, value in dict(contracts or {}).items()
        }
        self.semantic_checker = semantic_checker
        self.registry = registry or DEFAULT_SEMANTIC_REGISTRY

    def validate(self, graph):
        issues = []
        for node in graph.nodes:
            contract = self.contracts.get(node.ability)
            declared_inputs = dict(node.input_types)
            declared_outputs = dict(node.output_types)
            for direction, declared in (
                ("input", declared_inputs),
                ("output", declared_outputs),
            ):
                for name, semantic_type in declared.items():
                    if not self.registry.exists(semantic_type):
                        issues.append(
                            GraphValidationIssue(
                                SemanticValidationCode.UNKNOWN_SEMANTIC_TYPE,
                                f"Unknown semantic {direction} type for "
                                f"{node.node_id}.{name}: {semantic_type}.",
                                node.node_id,
                                stage=GraphValidationStage.SEMANTIC,
                            )
                        )
            if contract is not None:
                issues.extend(
                    compare_type_maps(
                        contract.input_types,
                        declared_inputs,
                        node.node_id,
                        SemanticValidationCode.INPUT_TYPE_MISMATCH,
                        "input",
                        self.registry,
                    )
                )
                issues.extend(
                    compare_type_maps(
                        contract.output_types,
                        declared_outputs,
                        node.node_id,
                        SemanticValidationCode.OUTPUT_TYPE_MISMATCH,
                        "output",
                        self.registry,
                    )
                )
            for binding in node.input_bindings:
                expected = declared_inputs.get(binding.input_name, "")
                if not binding.source_node_id or not expected:
                    continue
                source = graph.node(binding.source_node_id)
                actual = source.output_types.get(binding.output_path or "$", "")
                if actual and not self.registry.compatible(actual, expected):
                    issues.append(
                        GraphValidationIssue(
                            SemanticValidationCode.INPUT_TYPE_MISMATCH,
                            f"Semantic type mismatch for {node.node_id}."
                            f"{binding.input_name}: expected {expected}, got {actual} "
                            f"from {source.node_id}.",
                            node.node_id,
                            stage=GraphValidationStage.SEMANTIC,
                        )
                    )
        if self.semantic_checker is not None:
            try:
                extra = self.semantic_checker(graph)
                issues.extend(normalize_semantic_issues(extra))
            except Exception as error:
                issues.append(
                    GraphValidationIssue(
                        SemanticValidationCode.SEMANTIC_CHECK_FAILED,
                        f"Semantic checker failed: {error}",
                        stage=GraphValidationStage.SEMANTIC,
                    )
                )
        return GraphValidationReport(
            graph.graph_id,
            tuple(
                issue
                if issue.stage is not None
                else replace(issue, stage=GraphValidationStage.SEMANTIC)
                for issue in issues
            ),
        )


def resolve_output_path(output, path):
    if not path:
        return output, output is not None
    current = output
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            if index < len(current):
                current = current[index]
                continue
        return None, False
    return current, True


def select_input_envelope(envelopes, binding):
    for envelope in tuple(envelopes or ()):
        input_id = str(getattr(envelope, "input_id", "") or "")
        source = enum_value(getattr(envelope, "source", ""))
        modality = enum_value(getattr(envelope, "modality", ""))
        if binding.input_id and input_id != binding.input_id:
            continue
        if binding.accepted_sources and source not in binding.accepted_sources:
            continue
        if binding.accepted_modalities and modality not in binding.accepted_modalities:
            continue
        return envelope
    return None


def resolve_envelope_path(envelope, path):
    if envelope is None:
        return None, False
    if not path or path == "$":
        return envelope, True
    current = envelope
    for part in str(path).split("."):
        if hasattr(current, part):
            current = getattr(current, part)
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None, False
    return current, True


def enum_value(value):
    return str(getattr(value, "value", value) or "")


def compare_type_maps(expected, actual, node_id, code, direction, registry):
    issues = []
    for name, expected_type in expected.items():
        actual_type = actual.get(name)
        if actual_type and not registry.compatible(actual_type, expected_type):
            issues.append(
                GraphValidationIssue(
                    code,
                    f"Ability semantic {direction} mismatch for {node_id}.{name}: "
                    f"expected {expected_type}, got {actual_type}.",
                    node_id,
                    stage=GraphValidationStage.SEMANTIC,
                )
            )
    return issues


def registry_get(registry, key):
    if registry is None:
        return None
    getter = getattr(registry, "get", None)
    return getter(key) if callable(getter) else registry.get(key)


def normalize_semantic_issues(values):
    if values is None or values is True:
        return []
    if values is False:
        return [
            GraphValidationIssue(
                SemanticValidationCode.SEMANTIC_CHECK_FAILED,
                "Semantic checker rejected the TaskGraph.",
            )
        ]
    if isinstance(values, (GraphValidationIssue, str)):
        values = (values,)
    result = []
    for value in values:
        if isinstance(value, GraphValidationIssue):
            result.append(value)
        elif isinstance(value, dict):
            result.append(GraphValidationIssue(**value))
        else:
            result.append(
                GraphValidationIssue(
                    SemanticValidationCode.SEMANTIC_CHECK_FAILED,
                    str(value),
                )
            )
    return result


def permission_issue(decision, node_id, ability=""):
    if decision is None or decision is True:
        return None
    status = str(getattr(decision, "status", decision)).lower()
    reason = str(getattr(decision, "reason", "") or "")
    level = enum_value(getattr(decision, "level", ""))
    details = {
        "reason": reason,
        "ability": str(ability or ""),
        "risk": level or "unknown",
        "decision": enum_value(getattr(decision, "status", decision)),
    }
    if "confirm" in status:
        return GraphValidationIssue(
            GraphValidationCode.PERMISSION_CONFIRM_REQUIRED,
            reason or f"Permission confirmation is required: {node_id}",
            node_id,
            details=details,
        )
    allowed = getattr(decision, "allowed", None)
    if decision is False or allowed is False or "denied" in status or "restricted" in status:
        return GraphValidationIssue(
            GraphValidationCode.PERMISSION_DENIED,
            reason or f"Permission denied: {node_id}",
            node_id,
            details=details,
        )
    return None


def validation_code_for_error(message):
    lowered = message.lower()
    if "acyclic" in lowered:
        return GraphValidationCode.CYCLE
    if "dependencies" in lowered or "dependency" in lowered:
        return GraphValidationCode.MISSING_DEPENDENCY
    if "input" in lowered:
        return GraphValidationCode.INVALID_INPUT_BINDING
    if "unique" in lowered:
        return GraphValidationCode.DUPLICATE_NODE
    return GraphValidationCode.EMPTY


def replace_node(graph, updated_node):
    return replace(
        graph,
        nodes=tuple(
            updated_node if node.node_id == updated_node.node_id else node
            for node in graph.nodes
        ),
    )


def derive_graph_state(graph):
    states = {node.state for node in graph.nodes}
    if states and states <= {NodeState.COMPLETED, NodeState.SKIPPED}:
        return GraphState.COMPLETED
    if NodeState.FAILED in states:
        return (
            GraphState.PARTIAL_SUCCESS
            if NodeState.COMPLETED in states
            else GraphState.FAILED
        )
    if NodeState.WAIT_CONFIRM in states:
        return GraphState.WAIT_CONFIRM
    if NodeState.SUSPENDED in states:
        return GraphState.SUSPENDED
    return GraphState.RUNNING


def task_graph_fingerprint(graph):
    safe = {
        "graph_id": graph.graph_id,
        "task_id": graph.task_id,
        "version": graph.version,
        "revision": graph.revision,
        "state": graph.state.value,
        "nodes": [
            {
                "node_id": node.node_id,
                "ability": node.ability,
                "dependencies": node.dependencies,
                "state": node.state.value,
                "attempts": node.attempts,
                "turn_ids": node.turn_ids,
                "artifact_ids": tuple(item.artifact_id for item in node.artifact_refs),
                "memory_refs": node.memory_refs,
            }
            for node in graph.nodes
        ],
    }
    encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
