# Execution Cost Model

## Purpose

The Cost Model lets Plan Compiler select a cheaper or faster implementation
only when Registry metadata proves that the result and safety contract are
equivalent.

```text
Capability Operation
  -> equivalent implementation candidates
  -> safety compatibility filter
  -> cost ranking
  -> selected execution_target
```

## Operation Metadata

Each `CapabilityOperationMetadata` may declare:

```text
implementation_id
result_equivalence_key
estimated_cost
estimated_latency_ms
network_required
```

`estimated_cost` is a non-negative normalized planning value. It is not
currency unless a provider-specific adapter explicitly defines that mapping.
Latency is an estimate in milliseconds. `network_required` identifies external
network work for planning and diagnostics.

## Candidate Safety

Candidates are comparable only when all of these match the primary operation:

- result equivalence key;
- permission;
- side effect;
- input schema;
- output schema;
- lifecycle state;
- supported contract version.

A cheaper candidate that changes permission, side effects, schema, lifecycle,
or result semantics is excluded.

Cache candidates must explicitly claim the same result-equivalence contract.
Freshness, invalidation, and consistency guarantees belong in that candidate's
Registry implementation contract; a name containing `cache` proves nothing.

## Ranking

Compatible candidates use this deterministic order:

1. lowest `estimated_cost`;
2. lowest `estimated_latency_ms`;
3. local before `network_required`;
4. stable lexical `implementation_id` tie-break.

The selection is `OPT-005 Cost-based Implementation Selection`.

## Optimization Journal

An `OPT-005` entry records:

```text
step_id
before implementation
after implementation
estimated cost before and after
estimated latency before and after
network operations before and after
```

Goal, permission, side effects, and user-approved inputs remain unchanged.

## Plan Cost

`estimate_plan_cost()` returns:

```text
estimated_cost
estimated_latency_ms
network_operations
```

The current latency estimate is serial and conservative. Parallel critical-path
latency belongs to a later scheduler-aware cost model.

## Execution Boundary

Sprint 18.2.1 fixes `execution_target` in the execution-ready `AgentPlan`.
The legacy Runtime does not dispatch this target yet.

Sprint 18.5 Registry Composition will resolve `execution_target` to an actual
Ability/Provider adapter. Until that migration, Cost Model selection is
validated and journaled but does not alter the legacy execution route.

## Future Extensions

- provider price tables and quotas;
- observed latency moving averages;
- cache freshness and staleness budgets;
- reliability and retry cost;
- parallel critical-path estimation;
- user constraints such as local-only or no-paid-API.
