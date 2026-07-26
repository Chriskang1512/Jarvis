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

### Sprint 18.6 Implemented

1. `ExecutionJournal`, `JournalEntry`, phase contracts, artifact references, and
   the in-memory append-only store are implemented.
2. TaskRunner records Goal, Plan, Registry selection, step execution,
   permission, recovery, verification, and final-result decisions.
3. StateMachine events flow through EventBus into the same task sequence.
4. Every entry is chained to the previous entry with a deterministic SHA-256
   fingerprint.
5. `replay()` validates ordering and chain integrity without re-invoking an
   Ability or external side effect.
6. `explain()` returns recorded decision reasons and selected implementations.
7. JSON serialization/restoration and phase/event/status queries are
   implemented.
8. Metadata is allowlisted; sensitive keys and email-shaped values are dropped
   before append.

### Remaining Durable Migration

1. Build TaskHistory from the Journal projection and compare it with the
   existing in-memory compatibility history.
2. Add a durable local store with atomic append and retention controls.
3. Make checkpoint/journal persistence atomic for pause and external writes.
4. Switch resume and history reads to durable Journal projections.
5. Retire console trace parsing as a source of execution truth.

`Replay` in Sprint 18.6 is an audit replay. It reconstructs and validates the
decision history but never repeats provider calls or side effects.

## Operator Views

All views are projections over sanitized Journal entries:

```python
journal.timeline(task_id)
journal.tree(task_id)
journal.explain_why(task_id)
journal.search("최근 실패")
journal.export("journal.html", task_id=task_id)
```

`timeline()` renders millisecond timestamps, phases, events, and statuses in
append order. `tree()` groups entries by the order in which phases first
occurred. `explain_why()` shows selected capabilities, permission boundaries,
recovery decisions, verification, and terminal outcomes as a causal path.

Search recognizes operational categories including failures, retries,
Calendar, Gmail/Mail, OAuth/reauthentication, and paused tasks. It searches only
phase, event, status, and allowlisted metadata; it never searches raw user
content.

Export supports:

- `.json` for machine replay and comparison;
- `.md` for issue and pull-request reports;
- `.html` for a standalone human-readable report.

Markdown and HTML exports contain Timeline, Tree, and Explain Why views.
Every format inherits the Journal metadata allowlist and cannot restore data
that was discarded by the privacy boundary.
