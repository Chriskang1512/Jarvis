# NativeTaskGraph v1.4 — Sprint 2 Draft

This draft fixes the model boundary for the next sprint; it is not executable.

## Aggregate

- `NativeTaskGraph`: graph id, goal id, version, nodes, edges, outputs, policy
- `TaskNode`: node id, capability id, operation, input/output bindings,
  permission, retry, verification, state
- `TaskEdge`: source node, target node, dependency/condition
- `GraphOutput`: name plus a typed binding

## Binding kinds

`Literal`, `GoalInput`, `ContextSlot`, `NodeOutput`, `PreviousResult`,
`UserPreference`, `ArtifactReference`, and `SystemValue`.

Every binding carries a declared value type. A `NodeOutput` binding identifies
both `source_node_id` and `output_key`; raw string interpolation is not part of
the contract.

## Initial execution limits

Sprint 2 represents a single node, sequential nodes, and conditional skip.
Parallel fan-out/fan-in, loops, and multi-agent ownership remain out of scope.

## Serialization invariants

- IDs and binding kinds serialize as stable strings.
- JSON round-trips preserve typed values and policy defaults.
- Graphs do not embed provider clients, callbacks, or runtime exceptions.
- The future validator owns capability, cycle, binding, and permission checks.
