# ADR 0031: Runtime Service and Dashboard Interaction

- Status: Accepted
- Date: 2026-07-27
- Sprint: Jarvis v1.3 Sprint 22

## Context

The first Dashboard was a read-only client of an in-process Observability Hub.
Jarvis needs one local Core while CLI, local voice and browser interaction remain
replaceable adapters. Duplicating Planner or Ability execution in JavaScript
would violate that boundary.

## Decision

Introduce `JarvisRuntimeService` as the interactive application boundary.

```text
Browser text / Browser audio / Local microphone
  -> InputManager
  -> InputEnvelope
  -> JarvisRuntimeService
  -> VoicePipeline
  -> Planner / Memory / Ability
  -> interaction.result + EventBus trace
```

Dashboard WebSocket is bidirectional. It accepts `input.text` and `input.audio`
messages and emits `interaction.status`, `interaction.result` and
`interaction.error`. Browser audio uses MediaRecorder WebM/Opus, is transcribed
by the configured OpenAI STT path, and is not persisted. OpenAI TTS audio is
returned to the browser as a local WebSocket payload and removed from temporary
storage after reading. Other TTS configurations fall back to browser speech
synthesis for this first vertical slice.

Local wake turns and browser turns share a reentrant execution lock because the
current VoicePipeline owns mutable execution state. Browser turns use a distinct
VoiceSession, conversation session, and working-memory session so Dashboard
follow-ups cannot mutate the local microphone session.

Dashboard interaction owns the Wake lifecycle for the whole browser turn:

```text
Dashboard input
  -> pause Wake providers and Wake STT
  -> Planner / Ability
  -> Browser TTS playback
  -> tts.playback.finished
  -> resume Wake
```

The server does not resume Wake when audio generation or WebSocket delivery
finishes. The browser acknowledges actual audio/speech-synthesis completion.
Pending Wake events are discarded on pause, late transcription results from a
stopped monitor generation are ignored, and a race that already reached the
voice pipeline is rejected while the runtime is paused. A bounded server timer
is retained only as a fail-safe for abandoned browser clients.

Runtime ownership is expressed by `RuntimeTurnLock`, not by Dashboard-specific
conditionals. The lock manages a `RuntimeTurn` carrying owner, state, start time,
soft/hard timeout, typed priority, source, conversation ID, Task/Step links,
human-readable Turn ID, and a separate opaque LockToken. Every
turn is owned by one of `VOICE`,
`DASHBOARD`, `TOUCH_PORTAL`, `MOBILE`, `API`, `PLUGIN`, or `SCHEDULER`. Only that
token can release the runtime. `REJECT` returns a busy result immediately;
`WAIT` and `QUEUE` wait for the current owner, with optional timeout.

`PREEMPT` is cooperative and priority-gated. A higher-priority request changes
the current turn to `INTERRUPTING`, sets its cancellation signal, and waits for
the current execution checkpoint to release safely. The acquired emergency turn
starts only after cleanup; the lock is never forcibly stolen. Dashboard checks
before browser TTS generation and Voice checks before its follow-up loop.
Provider-level cancellation during an already-blocking STT, LLM, Ability, or TTS
call remains adapter work for later hardening.

Operational priority uses `TurnPriority`: `BACKGROUND=100`, `PLUGIN=200`,
`SCHEDULE=300`, `USER=500`, `EMERGENCY=900`, and `SYSTEM=1000`. Custom integers
remain possible but are labeled `CUSTOM`. Soft timeout publishes
`runtime.turn.timeout_warning`; hard timeout automatically requests cooperative
cancellation and publishes `runtime.turn.timeout`.

Waiting requests live in an explicit `RuntimeTurnQueue`, ordered by preempt
policy, descending priority, then insertion sequence. Releasing one Turn wakes
the queue and only its head may acquire, so execution continues automatically.
Task and Turn lifecycles remain distinct: one Task can be linked to multiple
Turns, while each Turn may execute one or more TaskSteps.

The lock publishes `runtime.lock.acquired`, `runtime.lock.busy`,
`runtime.lock.queued`, `runtime.turn.preempt_requested`, and
`runtime.lock.released`. Dashboard Runtime cards project the full active turn,
busy flag, and queue depth from these events.

## Consequences

- Dashboard becomes an interactive client without moving Core into the browser.
- Existing CLI/local voice execution remains available.
- Jarvis cannot hear its own browser TTS as a new wake/voice command.
- Keyboard and voice use the same provider-neutral InputEnvelope.
- Clipboard, image, OCR, file and mobile remain compatible future sources.
- WebSocket messages are limited to 16 MB and the server remains loopback-only.
- Audio streaming chunks and partial transcripts are deferred; Sprint 22 starts
  with complete push-to-talk clips.

## Operational UI projections

The sidebar Runtime Diagram and animated Event Flow are projections of the same
normalized event stream; they do not introduce a second state machine. Ability
latency is captured from `dispatcher.result` duration metadata. Memory type
counts are queried from the active MemoryManager and grouped into preference,
long-term, working, correction and personal lexicon categories.
