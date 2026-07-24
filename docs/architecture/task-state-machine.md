# Agent Core Task State Machine

## States

| State | Meaning | Terminal |
| --- | --- | --- |
| `PENDING` | Goal accepted; planning has not started | No |
| `PLANNING` | Planner is producing an AgentPlan | No |
| `VALIDATING` | Core is validating plan contracts and dependencies | No |
| `OPTIMIZING` | Core is applying auditable optimization rules | No |
| `READY` | Execution-ready plan accepted; no step started | No |
| `RUNNING` | Core may start or verify a step | No |
| `WAIT_CONFIRM` | A versioned confirmation is required | No |
| `WAIT_EXTERNAL` | External operation is still pending or being verified | No |
| `PAUSED` | A durable checkpoint exists and execution is intentionally suspended | No |
| `RESUMING` | Core is restoring and validating a checkpoint | No |
| `RETRYING` | A retry decision was journaled and the next attempt is pending | No |
| `VERIFYING` | Required execution results are being verified | No |
| `PARTIAL_SUCCESS` | At least one required outcome succeeded and another failed | Yes |
| `COMPLETED` | All required outcomes completed and verified | Yes |
| `FAILED` | Required outcome cannot safely complete | Yes |
| `CANCELLED` | User or policy cancelled remaining work | Yes |

New Agent Core flows use `COMPLETED`. The legacy TaskRunner adapter retains
`SUCCESS` after passing through `VERIFYING`, preserving existing serialized
responses until its callers migrate.

## State Transitions

| From | Event/guard | To |
| --- | --- | --- |
| `PENDING` | planning starts | `PLANNING` |
| `PLANNING` | AgentPlan produced | `VALIDATING` |
| `VALIDATING` | optimization required | `OPTIMIZING` |
| `OPTIMIZING` | optimized plan requires final validation | `VALIDATING` |
| `VALIDATING` | plan is execution ready | `READY` |
| `READY` | execution starts | `RUNNING` |
| `PENDING` | legacy execution adapter starts | `RUNNING` |
| `RUNNING` | confirmation required and request persisted | `WAIT_CONFIRM` |
| `WAIT_CONFIRM` | valid approval bound to current fingerprint | `RUNNING` |
| `WAIT_CONFIRM` | rejected or expired | `CANCELLED` or `PAUSED` |
| `RUNNING` | external response is non-terminal | `WAIT_EXTERNAL` |
| `WAIT_EXTERNAL` | verification proves success | `RUNNING` |
| `WAIT_EXTERNAL` | verification proves failure and retry allowed | `RETRYING` |
| `RUNNING` | pause requested and checkpoint persisted | `PAUSED` |
| `WAIT_CONFIRM` | pause requested and checkpoint persisted | `PAUSED` |
| `WAIT_EXTERNAL` | pause requested and checkpoint persisted | `PAUSED` |
| `PAUSED` | resume requested | `RESUMING` |
| `RESUMING` | checkpoint, side effects, fingerprints, and permission valid | `RUNNING` |
| `RESUMING` | external side effect is uncertain | `WAIT_EXTERNAL` |
| `RESUMING` | user input is required | `WAIT_CONFIRM` or `PAUSED` |
| `RETRYING` | checkpoint persisted and retry guard passes | `RUNNING` |
| any non-terminal | user cancels | `CANCELLED` |
| `RUNNING` | all required steps executed | `VERIFYING` |
| `VERIFYING` | all required results verified | `COMPLETED` |
| `RUNNING` | unrecoverable required step failure, no prior outcome | `FAILED` |
| `RUNNING` | unrecoverable failure after some outcomes | `PARTIAL_SUCCESS` |

## Normative Guards

### Pause

`PAUSED` may be entered only after checkpoint persistence succeeds. If storage
fails, the task remains in its prior state and execution must not silently
continue.

## Transition Engine

`TaskStateMachine.transition()` is the single state mutation boundary. It:

1. validates the requested edge against `ALLOWED_TRANSITIONS`;
2. appends a privacy-safe `StateTransitionRecord`;
3. creates and saves a checkpoint;
4. publishes the corresponding Core EventBus event;
5. returns the new immutable `RuntimeTask`.

Direct `task.state = ...` or dataclass replacement outside this boundary is
forbidden. Invalid edges fail with `INVALID_TASK_TRANSITION`. In particular,
`RUNNING -> COMPLETED` is blocked because `VERIFYING` is mandatory.

State transition history stores:

```text
transition_id
from_state
to_state
transition_reason
step_id
occurred_at
```

`transition_id` is a task-local, monotonically increasing integer and is also
used as the event revision and idempotency key suffix. `transition_reason` is a
stable reason code such as `permission_confirmation_required`,
`user_confirmed`, `network_timeout`, or `retry_started`; it must not contain
raw user input or provider payloads.

The legacy Python properties `sequence` and `reason` remain read-only aliases
during migration. Serialized history and EventBus payloads use only the
normative names. Sprint 18.6 may project these records into the durable
Execution Journal without changing the state engine.

### Resume

`RESUMING` performs, in order:

1. Load and validate checkpoint schema and checksum.
2. Restore task, plan version, bindings, artifacts, and step projections.
3. Reconcile completed and in-flight external operations.
4. Recompute and compare step input fingerprints.
5. Validate draft version and confirmation state.
6. Re-evaluate permission snapshot validity.
7. Determine the next safe step.
8. Persist the resume decision.
9. Enter `RUNNING` only after all guards pass.

`ResumeMode.FROM_STEP` and `FROM_CHECKPOINT` return to `RUNNING` after their
declared resume validation succeeds. `FULL_RESTART` returns to `PLANNING`.
Fingerprint mismatch escalates to `FULL_RESTART`; it never authorizes blind
repetition of a side effect.

## Events and Checkpoints

Foundation event types are:

```text
TaskStarted
TaskConfirmationRequired
TaskPaused
TaskResumed
TaskRetry
TaskCompleted
TaskCancelled
TaskFailed
TaskStateChanged
```

Every accepted transition saves a checkpoint before publishing its event.
The foundation uses `InMemoryTaskCheckpointStore`; the storage interface is
kept narrow so a durable store can replace it in a later Sprint.

Checkpoint fingerprints cover state, step position, completed/failed step IDs,
retry count, transition sequence, and privacy-safe step result metadata.
Responses, errors, goal text, and provider payloads are excluded.

### Retry

Retries are allowed only for classified retryable failures. A write step with an
unknown outcome must be verified before another provider call. Attempt count,
delay policy, and prior external operation ID are journaled.

### Cancellation

Cancellation stops future steps. It does not imply rollback of completed
external side effects. The final result must list completed outcomes and any
available compensating action.

## Step States

Task state and step state are separate. Step states are:

```text
PENDING
READY
RUNNING
WAIT_CONFIRM
WAIT_EXTERNAL
SUCCEEDED
FAILED
SKIPPED
CANCELLED
UNKNOWN_SIDE_EFFECT
```

A task may be `PAUSED` while its current step projection remains
`WAIT_CONFIRM`, `WAIT_EXTERNAL`, or `UNKNOWN_SIDE_EFFECT`.

## Invariants

- A completed step is not executed again without a new plan version.
- A side-effecting step has an input fingerprint before provider invocation.
- A confirmed step uses the exact confirmed fingerprint and draft version.
- A terminal task cannot return to a non-terminal state.
- Task transitions append to transition history and checkpoint before being
  published; durable Execution Journal integration belongs to Sprint 18.6.
- Provider objects and access tokens never enter task state.
