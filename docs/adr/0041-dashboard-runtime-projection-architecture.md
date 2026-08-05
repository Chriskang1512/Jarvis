# ADR 0041: Dashboard Runtime Projection Architecture

Status: Accepted

## Context

Jarvis Runtime events contain enough information to explain planning,
execution, verification, retries, permission waits, Memory persistence, and
Artifact creation. The existing observability surface normalized logs, but a
durable session-oriented read model is required for operations, future GUI,
Mobile, and replay.

## Decision

Dashboard Runtime is an event-driven CQRS read model:

```text
Runtime (source of truth)
→ immutable Runtime Event
→ SafeDashboardProjectionHandler
→ DashboardProjectionEngine
→ independent Projection Repository
→ REST / WebSocket
→ Browser
```

- Dashboard never receives Runtime command or mutation authority.
- Projection models are immutable and have an independent schema/runtime version.
- Every observed event receives a monotonically increasing `eventSequence`.
- Timeline order is based on that sequence, not browser arrival time.
- In-memory and SQLite repositories store sessions, the event journal, and
  periodic projection snapshots.
- Projections can be rebuilt from the journal; snapshots permit incremental
  restoration for long-running sessions.
- Health is explicitly `Healthy`, `Lag`, `Rebuilding`, or `Failed`.
- Projection subscriber failures are caught and counted and cannot change
  Planner, Executor, Memory, Artifact, or Provider outcomes.
- REST exposes running/recent sessions, detail, timeline, statistics, and health.
- WebSocket pushes projection/session/statistics updates; no polling loop is used
  for live session state.

## Shared Runtime State

`jarvis.runtime.RuntimeState` is the UI-neutral contract shared by Dashboard and
future Rive, Lively Wallpaper, Desktop Overlay, and Mobile clients:

`Idle`, `Listening`, `Thinking`, `Planning`, `Executing`,
`WaitingPermission`, `Verifying`, `Speaking`, `Completed`, and `Failed`.

Rive itself is deliberately deferred to the v1.7 GUI work.

## Privacy and coupling

Timeline details use an allowlist of operational identifiers and counters.
Provider raw responses, tokens, user content, and Runtime objects are not stored
in the Projection. Provider names are observations only; the Dashboard has no
Provider behavior dependency.

## Consequences

Jarvis can now be observed as an operating platform without creating a second
Runtime. Projection schemas and UI clients can evolve independently, and the
same Runtime State contract can feed future visual experiences.

The Sprint 3.5 operator experience remains a pure presentation of this read
model. It may aggregate and animate projected state for readability, but it
must not mutate Runtime, Graph, Session, Memory, Artifact, or Permission state.
Future Rive and mobile clients consume the same `RuntimeState` contract rather
than introducing UI-specific Runtime states.
