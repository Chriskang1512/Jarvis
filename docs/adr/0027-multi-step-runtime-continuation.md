# ADR 0027: Multi-step Runtime Continuation

## Status

Accepted

## Decision

A multi-step goal owns exactly one `RuntimeTask`. Confirmation and recovery
boundaries store `PendingPlanExecution` outside Abilities. The stored snapshot
contains the immutable plan, RuntimeTask, resolved execution context, prior
results, and the next safe step index.

Runtime exposes `confirm_task`, `cancel_task`, and `resume_task`. These methods
continue the existing Task and never invoke the natural-language Planner again.

Verification compensation is allowed only when an Ability explicitly implements
`rollback`. The Runtime does not invent inverse operations.

## Consequences

- Completed external writes are not repeated after confirmation or resume.
- Cancel can terminate the pending branch without undoing accepted prior work.
- Recovery remains policy-driven through `RecoveryDecision`.
- The default pending store is process-local. Durable implementations must
  encrypt protected artifacts and must not persist Mail content as plain JSON.
- Journal replay and explanation retain one causal Task history.
