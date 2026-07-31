# ADR 0036: Capability-aware Planning Architecture

Status: Accepted
Date: 2026-07-28

## Context

Sprint 2 established a safe NativeTaskGraph plan definition and deterministic
validation. Sprint 3 must create those plans without inventing capabilities,
provider choices, required values, or lower permissions. It must not execute
the plan.

## Decision

The planning pipeline is:

`GoalSpecification + CapabilityRegistrySnapshot`
` -> HybridPlanner -> NativeTaskGraph -> CapabilityPlanValidator -> PlannerResult`
` -> ExecutionPlanSnapshot -> GraphExecutor`

`ExecutionPlanSnapshot` is the immutable handoff record for a planned graph.
It contains GraphHash, trusted PlannerMetadata, PlanningConfidence, SnapshotId,
ValidationHash, and CreatedAt. PlanningConfidence is copied from PlannerResult
and remains a top-level execution-policy input. Snapshot creation revalidates
the graph and hashes canonical serializer and validation projections. It does
not contain node execution state, attempts, results, or errors. Those remain
the responsibility of the future GraphExecutionSession.

SnapshotVerifier is the fail-closed gate before GraphExecutor. It verifies the
graph and validation hashes, required planner metadata, supported snapshot
contract version, supported graph schema version, and confidence range. A
GraphExecutionSession cannot be created from a failed verification result.

Implementation order follows the diagnostic baseline:

1. CapabilityDescriptor and schemas
2. Immutable Registry Snapshot and stable RegistryHash
3. Deterministic RulePlanner
4. Registry/schema/permission validation
5. ExecutionPlan shadow comparison
6. Structured-output AIPlanner
7. Bounded repair loop

## Capability identity

Capability IDs are stable `domain.operation` identifiers, such as
`calendar.create_event`. Provider names are forbidden. The existing
AbilityRegistry is adapted operation-by-operation without modifying Direct
Execution. Provider selection remains an execution concern.

Snapshots contain only available or degraded descriptors. They are immutable,
carry disabled reasons separately, and hash the canonical descriptor content.
Snapshot identity and hash are recorded in graphs and diagnostics.

## Planner safety

RulePlanner is authoritative for the initial scenarios: weather lookup,
calendar search plus formatting, contact search, calendar creation,
conditional reminder creation, and weather-gated calendar update plus mail.
The latter resolves its target through `calendar.search_events` before
`calendar.update_event`. It binds typed descriptor inputs and copies descriptor
outputs, permissions, and verification support.

Core required inputs are never guessed. Missing location, date, event time,
contact query, title, reminder time, or reminder message returns
`NeedsUserInput`. A UserConfirmation node is reserved for approval after
concrete values are known.

CapabilityPlanValidator composes NativeTaskGraphValidator with snapshot
membership, operation, schema, permission, policy node-count, and success
criterion checks. A planned permission below the descriptor permission is an
error. AI output permissions are also replaced by the registry value before
the plan can be accepted.

## AI and repair

AIPlanner accepts JSON only and restores it through the NativeTaskGraph
serializer. Its prompt includes GoalSpecification, redacted-by-contract
SemanticContext, immutable capability snapshot, policy, schema requirements,
forbidden behavior, and a minimal binding example.

Invalid AI graphs are never returned as planned. HybridPlanner sends only the
invalid graph, structured validation issues, snapshot identity/capability
allow-list, original goal identity, and repair attempt to a bounded repair
loop. The default maximum is two. Failure or timeout returns no executable
graph.

## Shadow mode

ExecutionPlanShadowComparer compares capability order, permissions, and graph
outputs for diagnostics. It does not change the user response and does not
execute NativeTaskGraph. Existing execution remains authoritative.

## Voice runtime integration

Voice sends compound, conditional, result-dependent, previous-result, and
pause/resume goals to NativePlanningCoordinator before legacy planning.
`PlannerResult.Planned` is surfaced with diagnostics while
`native_execution_enabled` is false; the graph is not passed to an Ability or
legacy executor. Direct requests and single legacy-supported mutations retain
their existing execution path.

## Consequences

- The planner can only use capabilities present in its reproducible snapshot.
- Normal Rule graphs form a stable reference for AI diagnostics.
- PlannerResult explicitly distinguishes Planned, NeedsUserInput, Unsupported,
  Invalid, and Failed.
- NativeTaskGraph remains a plan definition. GraphExecutionSession and all
  Ability calls remain outside this sprint.

## Final hardening

NativeTaskGraph recursively freezes JSON-like metadata and InputBinding values.
Serialization creates a separate mutable JSON projection. Validation repair
must preserve GraphId and increment Version by exactly one; semantic replan is
reserved for a new graph identity with lineage metadata.

PlannerGraphMetadataEnricher overwrites untrusted planner metadata with
CapabilitySnapshotId, RegistryHash, PlannerType, PlannerVersion, and
PlanningPolicyVersion before validation. SuccessCriterion IDs originate in the
GoalSpecification and remain unchanged through graph mapping and verification.

`system.condition` emits `result`, `matched_branch`, structured `evidence`,
optional comparison values, and `operator`. Rule graphs contain explicit
ConditionalTrue and ConditionalFalse edges terminating in Result nodes, so a
false condition is a normal completion.

PlannerDiagnosticsSanitizer removes contact PII, secrets, paths, content
fields, and provider raw responses. Diagnostics retain input length/hash and
entity type/confidence without raw user or entity values.
