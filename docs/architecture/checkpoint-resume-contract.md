# Checkpoint and Resume Contract

## Purpose

A checkpoint is the durable boundary that makes pause, confirmation, retry, and
crash recovery safe. It is not a serialized Python object graph.

## Minimum Checkpoint Schema

```text
checkpoint_id
schema_version
task_id
plan_id
plan_version
task_state
current_step_id
completed_step_ids
pending_step_ids
step_input_fingerprints
external_operations
confirmation_state
draft_versions
permission_snapshots
bindings
artifact_refs
journal_sequence
checkpoint_created_at
resume_policy
checksum
```

The PM-required singular fields are represented as maps where a plan can have
multiple pending operations:

- `step_input_fingerprint` -> `step_input_fingerprints[step_id]`
- `external_operation_id` -> `external_operations[step_id].operation_id`
- `draft_version` -> `draft_versions[step_id]`
- `permission_snapshot` -> `permission_snapshots[step_id]`

## External Operation Record

```text
step_id
provider
operation
operation_id
idempotency_key
request_fingerprint
started_at
last_verified_at
status
verification_evidence_ref
```

Allowed status values:

```text
NOT_STARTED
IN_FLIGHT
SUCCEEDED
FAILED
UNKNOWN_SIDE_EFFECT
```

## Confirmation State

```text
confirmation_id
step_id
plan_version
input_fingerprint
draft_version
permission_level
requested_at
expires_at
decision
decided_at
```

Approval is invalid if any bound value changes or the confirmation expires.

## Permission Snapshot

```text
policy_version
step_id
capability
operation
permission_level
input_fingerprint
evaluated_at
expires_at
decision
reason_code
```

The snapshot proves what was evaluated. Core still re-evaluates on resume when
policy version, plan version, input, or expiry changed.

## Fingerprints

Fingerprints use canonical serialized, provider-independent input:

```text
sha256(schema_version + capability + operation + canonical_input)
```

Sensitive values may participate in the hash but are never stored in plaintext
solely for diagnostics. Salted or keyed hashes should be used where dictionary
attacks are realistic.

## Resume Algorithm

```text
load checkpoint
verify checksum and schema
load exact plan version
rebuild task projection from journal through journal_sequence
compare projection with checkpoint

for each completed or in-flight side-effect step:
    verify using provider verifier and external operation ID
    if succeeded:
        mark step SUCCEEDED
    elif failed:
        apply retry policy
    else:
        mark UNKNOWN_SIDE_EFFECT

recompute pending input fingerprints
invalidate changed confirmations and permission snapshots
resolve required bindings
choose earliest dependency-ready safe step
persist ResumeEvaluated
transition from RESUMING
```

## Unknown Side Effect Policy

If Core cannot determine whether an external write occurred:

```text
UNKNOWN_SIDE_EFFECT
  -> verification first
  -> no automatic re-execution
  -> user clarification if verification remains inconclusive
```

Examples:

- Gmail send timed out: search/verify using pending action ID, message ID, or
  deterministic headers before considering another send.
- Calendar create timed out: query by external operation ID or idempotency
  fingerprint before another create.
- Provider has no verifier: pause and explain that the result is uncertain.

## Resume Policies

| Policy | Behavior |
| --- | --- |
| `AUTO_SAFE` | Resume only read-only or proven-not-started steps |
| `VERIFY_THEN_RESUME` | Verify every external write before continuing |
| `RECONFIRM_WRITES` | Invalidate write confirmations and ask again |
| `USER_DECISION_REQUIRED` | Remain paused until clarification |
| `NEVER_RESUME` | Finalize as failed/cancelled according to policy |

Default for a plan containing external writes is `VERIFY_THEN_RESUME`.

## Storage Contract

Checkpoint storage provides atomic:

```text
save(checkpoint, expected_previous_version)
load(task_id)
list_resumable()
delete_after_terminal_retention(task_id)
```

Optimistic version checks prevent two runtimes from resuming the same task.
Journal append and checkpoint save must share an ordering contract even if the
first implementation uses one local transactional file/database.

## Privacy

- Never store OAuth tokens, auth headers, raw provider responses, or Gmail
  bodies in checkpoints.
- Store immutable draft references plus encrypted sensitive artifacts when the
  draft is required for resume.
- Logs expose task IDs, masked recipients, hashes, lengths, and reason codes.
- Checkpoint retention follows task sensitivity and user deletion policy.
