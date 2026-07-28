# ADR 0032: TaskGraph Execution Foundation

- Status: Accepted
- Date: 2026-07-27
- Target: Jarvis v1.4 Sprint 23 foundation

## Context

`RuntimeTask` owns a goal and its durable business lifecycle. `RuntimeTurn`
owns temporary access to the single interactive Runtime. Treating a graph node
as a Turn would make retry, resume, and provider timeout overwrite execution
history because one node may require several Turn attempts.

## Decision

Introduce a TaskGraph foundation without migrating the current linear Planner:

```text
RuntimeTask
  -> TaskGraph
  -> TaskNode
  -> RuntimeTurn[]
  -> Ability
  -> Provider
  -> TurnResult
```

`TaskGraph` is a validated DAG. Node IDs are unique, dependencies must exist,
self-dependencies and cycles are rejected, and only nodes whose dependencies
completed are READY. `TaskGraphCoordinator` checkpoints every accepted graph or
node mutation.

`TaskNode` stores Ability identity, dependencies, condition metadata, retry
policy, state, privacy-hidden input, structured output, Artifact references,
Memory references, and all Turn IDs used for its attempts.

`TurnResult` is the immutable execution-attempt result. It contains Task, Node,
and Turn identity, status, structured output, Artifact and Memory references,
error details, timestamps, and Provider metadata. Artifacts are referenced by
`ArtifactRef`; large files and Memory records are not embedded in checkpoints.
`InMemoryTurnResultStore` retains the full result by Turn ID and supports Node
history queries, while TaskNode keeps only the execution lineage and aggregate
output references needed for graph scheduling.

## Runtime integration

Acquiring a READY node creates a checkpointed transition:

```text
READY -> QUEUED -> RuntimeTurn acquired -> RUNNING
```

The Turn receives `task_id` and `step_id=node_id`. Recording its result appends
the Turn ID to the node and moves the node to COMPLETED, WAIT_CONFIRM, RETRYING,
or FAILED. A retry always receives a new Turn ID.

`TurnResult.provider_metadata` is projected into Graph observability, and
`TaskGraphCoordinator.record_tts` publishes an explicit Graph-correlated final
playback state. Core Graph completion and user-perceived TTS completion remain
distinct lifecycle facts.

Queue acquisition failure restores the node to READY. The graph checkpoint
fingerprint includes structural and lifecycle identity but excludes raw node
inputs and output contents.

## Data flow and preflight validation

Each `TaskNode` owns static `input`, runtime `output`, `required_inputs`, and
explicit `InputBinding` values. A binding maps an upstream node output (with an
optional dotted path) into a named downstream input. Binding sources must also
be declared dependencies, so control flow and data flow cannot silently
diverge. The coordinator materializes these inputs before acquiring a
`RuntimeTurn`.

`TaskGraphValidator` is the preflight gate for planner-created graphs. It
checks the DAG and dependency contracts, required input declarations, Ability
availability, Provider capability availability, and Permission decisions.
Existing registries are injected through their interfaces or checker callbacks;
TaskGraph does not own provider authentication or permission policy. A
coordinator configured with a validator refuses to start a graph with blocking
issues and emits `runtime.task_graph.validated`.

Validation has four explicit preflight stages:

```text
Structural -> Semantic -> Capability -> Permission -> Execution
```

Structural validation answers whether the graph can run. Semantic validation
answers whether it represents a coherent plan. Nodes declare semantic
`input_types` and `output_types`; bindings are rejected when an upstream type
cannot satisfy the downstream input type. `AbilitySemanticContract` can also
check a planner-created node contract against the Ability's expected contract.
`TaskGraphSemanticValidator` supports an injected semantic checker for richer
goal/intent checks without coupling the runtime model to one LLM provider.

Semantic types are canonical objects in `SemanticRegistry`, not free-form
runtime strings. The default registry includes `WeatherReport`, `HotelRecord`,
`HotelList`, `CalendarEvent`, `EmailDraft`, `Image`, `PDF`, `TaskPlan`,
`Summary`, and common base types. It owns aliases and parent compatibility, so
Abilities may declare stable semantic contracts while wire formats remain
serializable names.

`TaskGraphCapabilityValidator` separately verifies Ability registration and
Provider capability availability after semantic checks.
`TaskGraphPermissionValidator` then evaluates execution policy. The facade
`TaskGraphValidator` runs all stages in this order and annotates every issue
with its stage, while retaining its original construction API.
The facade measures every stage with a monotonic high-resolution clock and
serializes millisecond duration alongside pass/fail status.

`InputBinding` has two compatible source modes. A `source_node_id` binds graph
output; an omitted source node binds an external `InputEnvelope`. Envelope
bindings can select an input ID, source (`voice`, `keyboard`, `ocr`, `image`,
and others), modality, and a field path. This keeps multi-input normalization
inside `InputManager` while letting TaskGraph consume every surface through the
same binding contract.

## Consequences

- One Task can span many Turns and one node can retain many execution attempts.
- Parallel-ready nodes can be discovered without yet changing Planner behavior.
- Retry, resume, checkpoint, user confirmation, and Artifact lineage have stable
  extension points for Work-style Agents.
- Structurally valid but semantically inconsistent plans can be blocked before
  acquiring a Runtime Turn.
- Voice, keyboard, OCR, image, clipboard, file, mobile, and API inputs can feed
  graph nodes without adding source-specific Planner branches.
- Planner continues producing `ExecutionPlan`; runtime now validates and
  observes its TaskGraph projection while TaskRunner remains authoritative.
- The checkpoint store is in-memory for this foundation; durable persistence and
  crash recovery remain Sprint 23 work.
## Migration decision

`ExecutionPlan` remains the Planner's authoritative output during the migration
window. Runtime converts it through `ExecutionPlanAdapter`, validates the
resulting `TaskGraph`, and compares order, abilities, dependency execution
shape, and privacy-safe input fingerprints before execution.

```text
Planner -> ExecutionPlan -> ExecutionPlanAdapter -> TaskGraph
        -> GraphExecutor -> TaskRunner -> Ability
```

`GraphExecutor` does not execute an Ability a second time. It projects the
existing `TaskRunner` lifecycle onto graph nodes, while `TaskRunner` remains
authoritative for permission confirmation, retries, recovery, checkpoints, and
side effects. A comparison mismatch blocks execution and emits
`runtime.task_graph.shadow_compared`.

Removal of `ExecutionPlan` requires several sprints of comparison telemetry
with no unexplained mismatches. Until then, TaskGraph is a validated execution
projection rather than a second source of side effects.
