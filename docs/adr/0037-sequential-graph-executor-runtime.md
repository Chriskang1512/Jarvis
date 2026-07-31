# ADR 0037: Sequential GraphExecutor Runtime

Status: Accepted
Date: 2026-07-28

## Context

Sprint 3 produces immutable, validated NativeTaskGraph plans and immutable
ExecutionPlanSnapshot audit records. Sprint 4 must execute those contracts
without adding runtime state to the graph definition.

## Decision

The execution boundary is:

`PlannerResult -> ExecutionPlanSnapshot -> SnapshotVerifier`
` -> GraphExecutionSession -> Sequential GraphExecutor`

SnapshotVerifier is fail-closed. GraphHash, ValidationHash, required planner
metadata, snapshot contract version, and graph schema version must pass before
session creation. Successful verification emits
`runtime.execution.snapshot_verified`.

GraphExecutionSession owns all mutable state: SessionId, the unchanged
SnapshotId, graph identity, node records, typed OutputStore, timeline, state,
and checkpoint revision. NativeTaskGraph remains immutable.

TaskEdge is the dependency source of truth. The scheduler executes one Ready
node at a time. NodeOutput bindings read typed values from OutputStore instead
of concatenating text. ConditionalTrue and ConditionalFalse edges select a
single branch; the other branch is marked Skipped.

ConfirmRequired nodes pause before the Ability call after their inputs are
resolved. Approval resumes the same SessionId and SnapshotId. Restricted nodes
fail closed. Sprint 4 does not retry, replan, run in parallel, fan out, fan in,
or loop.

CapabilityExecutionAdapter maps provider-neutral CapabilityId and Operation to
the existing AbilityRegistry. Condition, Transform, Result, and NoOp nodes are
deterministic system operations.

Every checkpoint carries SnapshotId. Restore rejects a SnapshotId, GraphId, or
GraphVersion mismatch. GraphExecutionTimeline appends lifecycle events for
replay, diagnostics, and metrics.

Terminal sessions produce an immutable ExecutionSummary containing SessionId,
SnapshotId, duration, succeeded/skipped/failed node IDs, accumulated permission
wait time, provider call count, artifact descriptors, and a canonical
ResultHash. The same summary is attached to GraphExecutionResult, the terminal
checkpoint, and `runtime.execution.session_completed`. It contains artifact
identity only, not artifact contents or sensitive node outputs.

## Events

- runtime.execution.snapshot_verified
- runtime.execution.snapshot_verification_failed
- runtime.execution.session_created
- runtime.execution.node_ready
- runtime.execution.node_started
- runtime.execution.node_completed
- runtime.execution.node_skipped
- runtime.execution.session_completed

All lifecycle events after session creation carry SnapshotId, SessionId, and
GraphId. Event payloads exclude resolved inputs and provider data.

## Runtime activation

`JARVIS_NATIVE_EXECUTION_ENABLED=true` enables Native Graph execution in the
Voice runtime. The default remains false. When disabled, the validated plan is
reported without dispatch. When enabled, NativePlanningCoordinator passes the
Graph, ExecutionPlanSnapshot, and ValidationReport to GraphExecutor.

## Consequences

- Audit lineage is `SnapshotId -> SessionId -> Checkpoint -> Node event`.
- A failed snapshot verification cannot create an execution session.
- A false condition is successful completion, not an execution failure.
- Existing Direct Execution remains available and unchanged.
- Retry and replan remain deferred.
