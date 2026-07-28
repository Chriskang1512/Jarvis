# ADR 0030: Dashboard Observability Event Bridge

- Status: Accepted
- Date: 2026-07-27
- Sprint: Jarvis v1.3 Sprint 21

## Context

Jarvis already exposes runtime facts through EventBus, structured planner traces,
diagnostics, task state and memory stores. A dashboard that reads each subsystem
directly would become a second runtime and make displayed state disagree with
actual execution.

## Decision

Introduce a presentation-only `DashboardEventBridge` and bounded
`ObservabilityHub`.

```text
Jarvis Runtime
  -> EventBus / structured trace
  -> Dashboard Event Bridge
  -> Observability Hub
  -> HTTP API + WebSocket
  -> Web Dashboard
```

The hub normalizes every observation into `type`, `category`, `level`,
`timestamp` and `payload`. Timeline, Event Viewer, Logs and Planner Trace are
projections of this same stream. The server binds to loopback by default and
uses no cloud service or vendor-specific SDK.

Settings edits reject secret-like fields. Memory deletion remains an explicit
HTTP action routed through `MemoryManager`. Stub plugin and ability inventory
endpoints preserve the Sprint boundary without adding lifecycle mutations.

## Consequences

- The UI can be replaced without changing Jarvis Core.
- Planner traces remain observable even when console debug output is disabled.
- WebSocket clients receive a snapshot before incremental events.
- History is intentionally bounded and process-local; durable storage is deferred.

## TaskGraph preflight diagnostics

`runtime.task_graph.validated` carries the complete validation report, including
Structural, Semantic, Capability, and Permission stage status. The Hub retains
the latest report per Graph and exposes it through the snapshot, WebSocket, and
`/api/task-graphs/validation`. The Tasks view renders each stage and expandable
issue details such as reason, Ability, and risk.

The Tasks sidebar also projects the latest report as `Validation Health`.
Structural, Semantic, Capability, and Permission are independently colored and
expandable. Failure details include reason, Ability, risk, Node ID, and stable
validation code, making preflight rejection inspectable without reading logs.
Each gate also carries its measured `duration_ms`, allowing Registry growth or
external policy latency to be diagnosed from the same card.

The Graph projection continues through the complete user-perceived turn:

```text
Validation -> Execution -> Provider -> Result -> Memory -> TTS
```

Checkpoint events drive Execution. Node-result Provider metadata drives
Provider and Result, while actual `TurnResult.memory_refs` drive Memory. An
empty Memory reference list is shown as `NO_CHANGE`, never as a fabricated
update.

TTS completes only from a Graph-correlated `runtime.task_graph.tts` event or a
playback event carrying `graph_id`. Uncorrelated Voice playback cannot complete
an arbitrary Graph. This keeps the user-facing completion boundary at actual
playback without guessing across concurrent tasks.

`/api/semantic-types` exposes the canonical Semantic Registry inventory and
hierarchy. This is a read-only projection; Registry ownership remains in
Jarvis Runtime rather than Dashboard.

## Sprint 21 completion extensions

The same normalized stream also drives cumulative runtime metrics and the
animated Event Flow. Provider Monitor derives configured provider identity from
Settings and overlays the latest matching event latency/failure. Ability
Monitor derives readiness from the loaded Capability Registry. Entity Graph is
reserved in navigation but deliberately has no runtime implementation before
Sprint 22–23.
