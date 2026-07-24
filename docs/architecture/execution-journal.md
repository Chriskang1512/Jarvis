# Agent Core Execution Journal

## Purpose

The Execution Journal is the ordered, durable record of what Jarvis planned,
decided, attempted, verified, and produced. It supports:

- safe checkpoint reconstruction;
- "What did you do earlier?" task history;
- retry and side-effect investigation;
- Memory integration through privacy-safe projections;
- operational metrics without parsing console logs.

TaskHistory becomes a cache/projection. The Journal is authoritative.

## Event Envelope

```text
event_id
schema_version
sequence
task_id
plan_id
plan_version
event_type
step_id
timestamp
actor
correlation_id
causation_id
payload
privacy_class
payload_hash
```

Events are append-only. Corrections append a new event; they do not rewrite
history.

## Required Event Types

### Goal and Planning

```text
GoalAccepted
PlanProposed
PlanValidationCompleted
PlanOptimizationCompleted
PlanAccepted
PlanRejected
```

### Task Lifecycle

```text
TaskCreated
TaskStateChanged
CheckpointSaved
ResumeRequested
ResumeEvaluated
TaskCompleted
TaskFailed
TaskCancelled
```

### Step Lifecycle

```text
StepReady
StepStarted
StepAttempted
StepValidationCompleted
StepVerificationCompleted
StepSucceeded
StepFailed
StepRetryScheduled
UnknownSideEffectDetected
```

### Permission and Conversation

```text
PermissionEvaluated
ConfirmationRequested
ConfirmationDecided
ConfirmationExpired
ClarificationRequested
ClarificationResolved
TaskPaused
```

### Artifacts

```text
ArtifactCreated
ArtifactVerified
ArtifactDiscarded
```

## Artifact References

Journal events store references, never provider objects:

```text
artifact_id
artifact_type
version
storage_ref
content_hash
media_type
size
sensitivity
expires_at
```

Examples include a frozen mail draft, normalized Calendar event, generated
file, or verification evidence.

## Sensitive Data Policy

| Data | Journal representation |
| --- | --- |
| OAuth token / auth header | Never stored |
| Full email address | Masked display value plus keyed fingerprint |
| Mail subject | Hash; optional redacted preview |
| Mail body | Length, hash, encrypted artifact reference when resume requires it |
| Contact phone/email | Masked value and contact ID |
| Calendar description/participants | Redacted summary or protected artifact |
| Raw voice transcript | Protected source reference and normalized intent summary |
| Provider exception | Stable error code and safe message key |
| Provider response | Normalized IDs and verification facts only |

Journal readers enforce purpose-based views:

- runtime recovery may access protected artifacts;
- user task history receives a redacted natural-language projection;
- diagnostics receives IDs, timing, counts, hashes, and codes;
- Memory receives only explicitly approved durable facts.

## Ordering and Atomicity

- Sequence is monotonic per task.
- A state transition is valid only after its event append succeeds.
- `PAUSED` requires `CheckpointSaved` before `TaskStateChanged(PAUSED)`.
- Provider invocation requires `StepAttempted` with input fingerprint first.
- Successful writes require verification evidence before `StepSucceeded`.
- EventBus publication happens after durable append.

## Projections

The first projections are:

1. `RuntimeTaskProjection`: current state and step statuses.
2. `TaskHistoryProjection`: recent user-readable outcomes.
3. `MetricsProjection`: latency, retries, failures, confirmations, resumes.
4. `ResumableTaskProjection`: tasks in wait/pause/external states.
5. `ArtifactProjection`: artifact retention and deletion schedule.

## "What Did You Do Earlier?"

The history formatter reads verified journal events and returns:

```text
오늘 오후 3시 일정을 등록했고,
하루 전 알림을 설정했으며,
아야에게 보낼 메일은 확인을 기다리고 있습니다.
```

It must distinguish completed, pending, failed, cancelled, and uncertain side
effects. It must never claim success from an API request alone.

## Retention

- Terminal task metadata may be retained longer than sensitive artifacts.
- Sensitive draft artifacts expire after task completion unless policy requires
  audit retention.
- Users can delete task history and associated artifacts.
- Compaction may create signed snapshots, but source events remain immutable
  until their retention period ends.

## Migration

1. Define journal interfaces and in-memory implementation.
2. Mirror current TaskRunner lifecycle into journal events.
3. Build TaskHistory from journal projection and compare with existing history.
4. Add durable local storage and checkpoint ordering.
5. Switch resume and history reads to journal projections.
6. Retire console trace parsing as a source of execution truth.
