# Plan Validator and Optimizer

## Scope

Sprint 18.2 turns a proposed `AgentPlan` into an execution-ready plan:

```text
Proposed AgentPlan
  -> Registry Schema Validator
  -> Dependency Graph Validator
  -> Smart Plan Optimizer
  -> Revalidation
  -> Execution Ready Plan
```

Planner proposes. Core decides whether execution is allowed.

## Operation Registry

`AbilityRegistry` owns normalized `CapabilityOperationMetadata`:

```text
capability
operation
input_schema
output_schema
permission
contract_version
lifecycle
side_effect
input_schema_version
output_schema_version
parallel_safe
deduplicatable
required_predecessors
estimated_cost
estimated_latency_ms
network_required
availability
reliability_score
```

Existing Abilities receive compatibility operation metadata during
registration. New operation-level metadata may replace those defaults
explicitly.

An Ability ID does not prove an operation exists. `calendar.creat` is blocked
as `UNKNOWN_OPERATION` even when the Calendar Ability is registered.

## Validation

The Validator checks:

1. Plan contract version.
2. Unique step IDs.
3. Capability existence.
4. Operation existence.
5. Input schema and fields satisfied directly or by bindings.
6. Output schema presence.
7. Input and output schema versions.
8. Permission equality with Registry policy.
9. Side-effect equality with Registry policy.
10. Verification and idempotency for external writes.
11. Lifecycle state.
12. Dependency references and required predecessors.
13. Binding source and target steps.
14. Binding source represented by a target dependency edge.
15. Dependency cycle detection.

Stable result levels:

```text
VALID    -> execution allowed
WARNING  -> execution allowed with structured issues
BLOCKED  -> execution forbidden
```

Experimental lifecycle information is non-blocking. Deprecated operations
produce `WARNING`. Sunset operations produce `BLOCKED`.

## Dependency Graph

Dependencies use `step_id`, not tuple position. Planner output order is not
trusted.

A binding such as:

```text
contacts.get.output.email
  -> mail.send.input.to
```

requires the Mail step to declare the Contacts step in `depends_on`. A missing
edge is `DEPENDENCY_MISSING`. Cycles are `DEPENDENCY_CYCLE`.

## Optimizer Rules

The Smart Optimizer is conservative and auditable:

| Rule | Name | Behavior |
| --- | --- | --- |
| `OPT-001` | Duplicate Removal | Removes identical Registry-approved deduplicatable safe operations and rewires references |
| `OPT-002` | Dependency Reorder | Restores stable topological order |
| `OPT-003` | Parallel Merge | Assigns a parallel group to independent Registry-approved safe operations |
| `OPT-004` | Dead Step Removal | Removes only unreferenced optional safe steps explicitly marked `_dead_step` |
| `OPT-005` | Cost Selection | Selects the cheapest and fastest safety-equivalent Registry implementation |

Every applied rule records:

```text
rule_id
reason
before_step_ids
after_step_ids
details
```

The Optimizer verifies that `goal_id`, required permissions, and every
side-effecting operation and input remain unchanged.

Execution cost metadata and candidate selection are defined in
[`execution-cost-model.md`](execution-cost-model.md).

## Compilation Boundary

`PlanCompiler` applies:

```text
Validate original
  -> BLOCKED: stop
  -> Optimize
  -> Validate optimized
  -> BLOCKED: stop
  -> return Execution Ready Plan
```

RuntimeTask must only accept the execution-ready result once migration reaches
the execution integration phase. Current legacy execution remains unchanged.

## Journal and Replay

Each validation decision stores a serializable plan snapshot and structured
result:

```text
plan_snapshot
validator_version
status
issues
```

Replay reconstructs only this snapshot, runs the same Validator, and compares
the complete status and ordered issue list. No provider object or raw exception
is required.

Journal snapshots redact input values while preserving validation-relevant
field names, container shape, and primitive types. Replay therefore reproduces
the current structural schema decision without retaining mail bodies,
addresses, or other sensitive values.

Optimization records store rule IDs, reasons, before/after step IDs, strict
fingerprints, and invariant verification.

## Privacy

Journal persistence must apply the Execution Journal privacy contract before
durable storage. Raw email bodies, addresses, OAuth data, provider payloads,
and unrestricted voice transcripts are not valid plan snapshot fields.

## Current Compatibility

- Existing `ExecutionPlan` execution is unchanged.
- Compatibility operation metadata is derived for current native Abilities.
- Operation-specific Registry metadata can replace compatibility defaults.
- Unregistered third-party Ability operations fail closed in the new
  Validator until they publish operation contracts.
