# Agent Core Planner Contract

## Principle

> AI turns a goal into a plan. Core validates, optimizes, executes, and
> remembers that plan.

The AI parser may propose structure. Only Core may accept a plan for execution.

## Pipeline

```text
GoalEnvelope
  -> ProposedPlan
  -> PlanValidator
  -> PlanOptimizer
  -> ExecutablePlan
  -> RuntimeTask
```

## Contract Version Negotiation

Planner and Runtime declare their supported and preferred contract versions
before a proposed plan is accepted:

```text
Planner ContractSupport
  -> highest common version
  -> registered Version Adapter path when no common version exists
  -> fail closed when neither is available
```

Versions normalize to stable labels such as `1.0`, `2.0`, and `2.1`.
`v2` and `2` both normalize to `2.0`.

Direct negotiation selects the highest common version. When no version is
shared, Core searches the directed `VersionAdapterRegistry` for the shortest
deterministic conversion path. For example:

```text
AgentPlan 3.0
  -> adapter 3.0-to-2.0
  -> adapter 2.0-to-1.0
  -> Runtime supporting 1.0
```

Adapters are explicit, deterministic Core code. Duplicate conversion edges,
missing paths, and unsupported preferred versions are rejected. The stable
failure code for an unresolvable producer/consumer pair is
`CONTRACT_VERSION_NOT_NEGOTIABLE`.

Negotiation changes representation only. It must not change the goal,
permissions, side effects, bindings, or semantic fingerprint.

### Capability Minimum Version

After contract negotiation and before plan validation/execution, Core checks
every `capability.operation` in the plan against operation-level requirements:

```text
Runtime support
  -> contract negotiation
  -> capability minimum-version gate
  -> Plan Validator
```

Each registered requirement declares:

```text
capability
min_contract
recommended
deprecated_after
sunset
```

If the selected version is below `min_contract`, execution fails with
`CAPABILITY_CONTRACT_VERSION_UNSUPPORTED`. If it meets the minimum but is below
`recommended`, execution may continue with the structured warning
`CAPABILITY_CONTRACT_VERSION_BELOW_RECOMMENDED`.

`negotiate_plan()` derives operation names such as `calendar.create` and
`mail.send` directly from Plan steps so callers cannot accidentally omit a
requested capability from the gate. Unregistered operations remain compatible
during the legacy metadata migration.

`deprecated_after` is a contract-version lifecycle boundary. A selected
version greater than that boundary remains executable but emits
`CAPABILITY_CONTRACT_DEPRECATED`.

`sunset` accepts `YYYY-MM` or `YYYY-MM-DD`; month-only values normalize to the
first day of that month. Before that date Core emits
`CAPABILITY_SUNSET_SCHEDULED`. On or after the date, execution fails closed
with `CAPABILITY_SUNSET_REACHED`. Runtime supplies the current date through an
injectable clock so replay and tests remain deterministic.

Future lifecycle maturity states are recorded in ADR 0025. The proposed flow is
`Experimental -> Stable -> Deprecated -> Sunset`. This remains a Registry
extension point and does not change current execution behavior.

## Goal Envelope

Minimum fields:

```text
goal_id
raw_text_ref
normalized_goal
requested_outcomes
constraints
conversation_id
created_at
source
```

`raw_text_ref` points to privacy-controlled input. Durable records should store
a hash or redacted summary instead of sensitive voice text.

## Plan

Minimum fields:

```text
plan_id
plan_version
planner_version
goal_id
status
steps
bindings
required_permissions
created_at
optimized_from_version
```

Every material mutation creates a new immutable `plan_version`.

## Step

```text
step_id
ordinal
capability
operation
input
input_schema_version
output_schema_version
depends_on
required
side_effect
permission
retry_policy
verification_policy
idempotency_policy
```

`capability` and `operation` are Registry identifiers. Provider and tool names
are resolved only at execution time.

## Bindings

A binding connects a prior output to a later input:

```text
source_step_id
source_path
target_step_id
target_path
transform
required
```

The Validator checks both schema paths and type compatibility. Transforms must
be registered deterministic Core transforms, never arbitrary AI code.

Example:

```text
calendar.create.output.event.start
  -> reminder.create.input.event_start
```

## Validation Stages

Validation is fail-closed and runs before optimization and again after it.

1. Contract version supported.
2. Every capability operation exists in Ability Registry.
3. Inputs satisfy operation schemas or have valid required bindings.
4. Outputs referenced by bindings exist.
5. Dependencies reference valid steps.
6. Dependency graph is acyclic.
7. Permission and side-effect metadata are present.
8. Required verification/idempotency policies exist for external writes.
9. No optimizer invariant is violated.

Validation produces structured issues:

```text
code
severity
step_id
field
message_key
```

Raw exceptions do not become user speech.

## Optimization

The Optimizer may:

- topologically order steps within user constraints;
- move prerequisite reads before dependent writes;
- remove provably duplicate safe reads;
- reuse a compatible prior output binding;
- group independent safe reads when the executor later supports concurrency.

The Optimizer must not:

- add or remove a requested outcome;
- weaken or bypass permission;
- add a side effect;
- change recipient, content, time, or other user-approved data;
- turn an optional step into required, or the reverse;
- remove verification or idempotency requirements.

Normative rule:

> The Optimizer may change order, but it must not change the user's goal,
> permissions, or side effects.

Every optimization records:

```text
optimizer_version
input_plan_version
output_plan_version
rules_applied
semantic_fingerprint_before
semantic_fingerprint_after
```

The semantic fingerprints must match. Otherwise optimization is rejected.

## Permission Boundary

Planner declares the required permission. Permission Layer decides it.
Confirmation is bound to:

```text
task_id + plan_version + step_id + input_fingerprint + draft_version
```

A plan change invalidates confirmation for affected steps.

## Initial Compatibility Strategy

Current `ExecutionPlan` and `ExecutionStep` remain adapters during migration.
The adapter maps `tool_name` to a Registry capability operation. New code must
not add more rule-specific context wiring to the legacy dictionaries.
