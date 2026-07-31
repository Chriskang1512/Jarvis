# GraphExecutor v1.4 — Sprint 4 Draft

Sprint 4 executes a previously validated NativeTaskGraph sequentially. It must
not mutate the plan definition.

## Plan handoff

The executor boundary is:

`PlannerResult -> ExecutionPlanSnapshot -> SnapshotVerifier -> GraphExecutor`

ExecutionPlanSnapshot records GraphHash, trusted PlannerMetadata, SnapshotId,
ValidationHash, PlanningConfidence, and CreatedAt. The snapshot is created only
after revalidation and lets audit and replay identify the exact accepted plan.
SnapshotVerifier must accept GraphHash, ValidationHash, required
PlannerMetadata, SnapshotVersion, and graph SchemaVersion before
GraphExecutionSession creation. Low PlanningConfidence can later select a
confirmation policy even when integrity verification succeeds.

After successful verification and before session creation, the executor emits:

`runtime.execution.snapshot_verified`

The event payload contains only operational audit fields:

- snapshot_id
- graph_id
- graph_hash
- validation_hash
- planning_confidence
- planner_type
- capability_snapshot_id
- graph_version
- schema_version
- verified_at
- correlation_id

Sensitive goal inputs, node bindings, message bodies, paths, and provider data
must not be included. The event is emitted exactly once for the logical
execution-session creation attempt. Emission does not imply that any node has
started.

If verification fails, the executor emits
`runtime.execution.snapshot_verification_failed` with SnapshotId, GraphId,
sanitized issue codes, version identifiers, and CorrelationId. It must not emit
`snapshot_verified` and must not create GraphExecutionSession.

## State boundary

`NativeTaskGraph` answers what to execute. A new `GraphExecutionSession` owns:

- SessionId, GraphId, GraphVersion, GoalId
- Graph state and per-node execution state
- Attempt counts and idempotency keys
- Resolved input snapshots
- Typed outputs and ArtifactRef values
- Errors, permission waits, timestamps, and checkpoint revision

## Initial execution flow

1. Verify ExecutionPlanSnapshot and the supplied graph/validation record.
2. Emit `runtime.execution.snapshot_verified`.
3. Create GraphExecutionSession.
4. Find the next pending node whose TaskEdge dependencies are satisfied.
5. Check and batch permission requirements.
6. Resolve typed InputBindings.
7. Dispatch the provider-neutral CapabilityId through the runtime registry.
8. Store declared outputs without changing TaskNode.
9. Apply VerificationPolicy.
10. Advance, retry, pause, or fail according to policy.
11. Persist an atomic GraphExecutionSession checkpoint.

## Initial limits

- Sequential only
- One active node
- Simple ConditionalTrue/ConditionalFalse skip
- No fan-out/fan-in
- No replanning
- No AI calls in the executor

## Safety invariants

- Idempotency key includes GoalId, GraphVersion, NodeId, and logical attempt.
- Confirmation occurs after all mutation values are resolved.
- Registry permission is authoritative at execution time as well as planning.
- Resume never repeats a succeeded external mutation.
- Provider results are verified against OutputDefinition before storage.
