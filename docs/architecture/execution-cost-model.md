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
availability
reliability_score
```

`estimated_cost` is a non-negative normalized planning value. It is not
currency unless a provider-specific adapter explicitly defines that mapping.
Latency is an estimate in milliseconds. `network_required` identifies external
network work for planning and diagnostics.

Availability is `ONLINE`, `DEGRADED`, or `OFFLINE`. Reliability is a normalized
score from `0.0` to `1.0`.

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

## Adaptive Selection

`ExecutionSelectionPolicy` supports two explicit strategies:

- reliability-first: availability, reliability, cost, latency, network use;
- cost-first: availability, cost, reliability, latency, network use.

`OFFLINE` candidates are excluded. `DEGRADED` candidates rank behind every
compatible `ONLINE` candidate. A configurable minimum reliability threshold
may exclude weak candidates.

When the primary target is unavailable but an equivalent ONLINE candidate
exists, Validator returns a warning so Optimizer can select the fallback.
When every compatible candidate is OFFLINE, Plan Compiler returns `BLOCKED`.

## Runtime Metrics

`AdaptiveExecutionCostModel` keeps a bounded recent observation window per
operation and implementation:

```text
success
latency_ms
cost
availability
```

Recent observations produce an effective reliability score, average latency,
average cost, and current availability. Runtime values override static
Registry estimates for selection without mutating Registry metadata.

A failed observation marks the implementation `DEGRADED`; a successful
observation marks it `ONLINE`. Runtime may explicitly set `OFFLINE` after a
health check or provider outage.

Metric records contain implementation IDs and numeric operational data only.
They must not contain user input or provider payloads.

## Health Reason and Recovery

Non-ONLINE profiles carry one stable reason:

```text
TIMEOUT
RATE_LIMIT
AUTH_FAILURE
NETWORK
SERVER_ERROR
UNKNOWN
```

ONLINE profiles always use `NONE`. A successful observation clears the prior
reason. A non-ONLINE state without an explicit reason normalizes to `UNKNOWN`.

`HealthRecoveryPolicy` maps reasons to structured actions:

| Reason | Strategy | Retry budget | Delay |
| --- | --- | --- | --- |
| `TIMEOUT` | `BACKOFF`, then `FALLBACK` | 3 | 30 seconds |
| `RATE_LIMIT` | `WAIT` | unlimited | 300 seconds |
| `AUTH_FAILURE` | `REAUTH` | 0 | external completion |
| `NETWORK` | `WAIT` | event driven | network restoration |
| `SERVER_ERROR` | `BACKOFF`, then `FALLBACK` | 5 | 60 seconds |
| `UNKNOWN` | `ABORT` | 0 | verification required |

`max_retry=None` means unlimited. `max_retry=0` means no automatic retry.
`strategy_for(retries_completed)` returns the normal strategy while budget
remains and the exhausted strategy afterward.

Recovery decisions serialize these stable fields:

```text
retry_allowed
retry_after_seconds
max_retry
recovery_strategy
exhausted_strategy
requires_reauthentication
priority
resume_mode
resume_validation
checkpoint_fingerprint
```

Recovery priority is `HIGH`, `NORMAL`, or `LOW`. `scheduler_key()` exposes the
stable ascending queue order `HIGH -> NORMAL -> LOW`.

Resume mode removes Reason-specific inference from Task State Machine:

| Reason | Priority | Resume mode |
| --- | --- | --- |
| `TIMEOUT` | `NORMAL` | `FROM_CHECKPOINT` |
| `RATE_LIMIT` | `LOW` | `FROM_STEP` |
| `AUTH_FAILURE` | `HIGH` | `FROM_STEP` |
| `NETWORK` | `HIGH` | `FROM_CHECKPOINT` |
| `SERVER_ERROR` | `NORMAL` | `FROM_CHECKPOINT` |
| `UNKNOWN` | `HIGH` | `FULL_RESTART` |

Resume validation is an independent contract:

| Reason | Resume validation |
| --- | --- |
| `TIMEOUT` | `CHECKPOINT` |
| `RATE_LIMIT` | `STEP_ONLY` |
| `AUTH_FAILURE` | `STEP_ONLY` |
| `NETWORK` | `CHECKPOINT` |
| `SERVER_ERROR` | `CHECKPOINT` |
| `UNKNOWN` | `FULL` |

The State Machine consumes `recovery_strategy`, `resume_mode`, and
`resume_validation`; it does not branch on Health Reason.

For `CHECKPOINT` and `FULL` validation, the decision is bound to a
privacy-safe `checkpoint_fingerprint` when the checkpoint is persisted.
A missing or changed fingerprint escalates the effective resume mode to
`FULL_RESTART`. This means full validation and replanning, not blind replay of
side effects. Unknown external writes still pass through the
`UNKNOWN_SIDE_EFFECT` verification gate.

Recovery decisions are policy data; Cost Model does not sleep, refresh OAuth,
or retry by itself. Sprint 18.3 Task State Machine consumes these decisions.

Validator issues include availability and reason. `OPT-005` Journal entries
record the health reason before and after target selection.

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

Sprint 18.5/18.6 will also connect Provider timeout, health, success, latency,
and cost events to `AdaptiveExecutionCostModel.observe()`.

## Future Extensions

- provider price tables and quotas;
- observed latency moving averages;
- cache freshness and staleness budgets;
- reliability and retry cost;
- parallel critical-path estimation;
- user constraints such as local-only or no-paid-API.
