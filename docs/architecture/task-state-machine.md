# Agent Core Task State Machine

## States

| State | Meaning | Terminal |
| --- | --- | --- |
| `PENDING` | Valid executable plan accepted; no step started | No |
| `RUNNING` | Core may start or verify a step | No |
| `WAIT_CONFIRM` | A versioned confirmation is required | No |
| `WAIT_EXTERNAL` | External operation is still pending or being verified | No |
| `PAUSED` | A durable checkpoint exists and execution is intentionally suspended | No |
| `RESUMING` | Core is restoring and validating a checkpoint | No |
| `RETRYING` | A retry decision was journaled and the next attempt is pending | No |
| `PARTIAL_SUCCESS` | At least one required outcome succeeded and another failed | Yes |
| `COMPLETED` | All required outcomes completed and verified | Yes |
| `FAILED` | Required outcome cannot safely complete | Yes |
| `CANCELLED` | User or policy cancelled remaining work | Yes |

The current `SUCCESS` value migrates to `COMPLETED`. Compatibility adapters may
read both during the transition.

## State Transitions

| From | Event/guard | To |
| --- | --- | --- |
| `PENDING` | plan validated and permissions allow first step | `RUNNING` |
| `RUNNING` | confirmation required and request persisted | `WAIT_CONFIRM` |
| `WAIT_CONFIRM` | valid approval bound to current fingerprint | `RUNNING` |
| `WAIT_CONFIRM` | rejected or expired | `CANCELLED` or `PAUSED` |
| `RUNNING` | external response is non-terminal | `WAIT_EXTERNAL` |
| `WAIT_EXTERNAL` | verification proves success | `RUNNING` or `COMPLETED` |
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
| `RUNNING` | all required steps verified | `COMPLETED` |
| `RUNNING` | unrecoverable required step failure, no prior outcome | `FAILED` |
| `RUNNING` | unrecoverable failure after some outcomes | `PARTIAL_SUCCESS` |

## Normative Guards

### Pause

`PAUSED` may be entered only after checkpoint persistence succeeds. If storage
fails, the task remains in its prior state and execution must not silently
continue.

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
- Task transitions append to the Execution Journal before being published.
- Provider objects and access tokens never enter task state.
