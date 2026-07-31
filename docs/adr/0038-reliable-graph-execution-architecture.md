# ADR 0038: Reliable Graph Execution Architecture

Status: Accepted

## Context

Sprint 4 can execute a validated immutable graph, but a provider call returning
without an exception is not sufficient evidence that the intended state was
reached. Transient failures, ambiguous mutation outcomes, invalid planning
assumptions, and process restarts need different recovery actions.

## Decision

Jarvis separates three mechanisms:

- Retry repeats the same logical node with the same idempotency key.
- Planner repair corrects an invalid graph before execution.
- Partial replan creates a new graph for the unfinished portion of a goal.

Every node result passes through schema verification and its declared
VerificationPolicy before entering OutputStore. Semantic verification compares
resolved inputs with normalized outputs. External mutations may use an
in-verifier read-back capability; read-back calls are counted as provider
calls but are not represented as goal nodes.

RetryController is a pure decision component. GraphExecutor owns scheduling,
waiting state, checkpointing, and retry execution. AttemptHistory stores only
operational identifiers, error categories/codes, timings, hashes,
verification status, and the stable idempotency key.

Not-found, multiple-candidate, and invalid-assumption failures create a
ReplanTrigger. ReplanController preserves completed node identities and
reusable outputs, creates a new GraphId with parentGraphId and
previousGraphVersion, validates it, creates a new snapshot, and starts a new
session under the same GoalExecutionId with PreviousSessionId lineage.

RecoveryController treats interrupted reads as retryable and interrupted
mutations as unknown. Mutations require read-back before success; an
inconclusive read-back pauses safely instead of repeating the side effect.

GoalVerifier evaluates mapped GoalSpecification success criteria after node
completion. Required criteria must pass. Optional failures can produce Partial
only when GraphExecutionPolicy allows partial completion.

## Rollout

- Verification defaults on.
- Retry defaults off.
- Replan defaults off.
- Provider fallback is permitted only by node policy and is disabled for
  external mutations.

## Consequences

Checkpoint and ExecutionSummary schemas now include attempts, verification,
retry/replan counts, outcome, graph/session lineage, and recovery paths.
Diagnostics and events exclude raw user text, contact values, message bodies,
tokens, file contents, and provider responses.
