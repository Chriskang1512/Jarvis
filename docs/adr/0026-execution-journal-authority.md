# ADR 0026 - Execution Journal Authority

## Status

Accepted for Sprint 18.6.

## Context

Jarvis already emits console traces, stores RuntimeTask transition history,
records EventBus events, and keeps a compatibility TaskHistory. Those records
answer different questions and cannot independently explain the complete
decision path from a Goal to a verified Result.

Agent Runtime operations need a privacy-safe, ordered record that can be
serialized, restored, audited, and explained without re-executing external
side effects.

## Decision

Execution Journal is the authoritative ordered record of Runtime decisions.
Logs remain diagnostic output, transition history remains task state, and
TaskHistory becomes a user-facing projection.

Each entry contains:

```text
id
timestamp
task_id
sequence
phase
event
status
metadata
previous_fingerprint
fingerprint
```

The supported phases are:

```text
GOAL
PLAN
DISCOVERY
VALIDATION
OPTIMIZATION
PERMISSION
EXECUTION
VERIFICATION
RECOVERY
CONVERSATION
RESULT
```

TaskRunner records decision boundaries. TaskStateMachine continues to publish
privacy-safe EventBus events, and the Journal subscribes to those events.
Both sources append into one task-scoped monotonic sequence.

Replay validates sequence and fingerprint-chain integrity. Replay does not call
Providers, Abilities, or external APIs.

Explain uses only recorded operational reasons and implementation-selection
facts. It does not reconstruct or expose the original user request.

## Privacy

Journal metadata is allowlisted. Raw user input, prompts, voice transcripts,
mail subjects and bodies, addresses, phone numbers, OAuth material, provider
payloads, and raw exceptions are prohibited.

Artifacts are represented by type, ID, fingerprint, verification state, size,
media type, and sensitivity. Artifact content is not embedded in Journal
entries.

## Consequences

- Runtime behavior can be inspected without parsing console logs.
- Tampered or incomplete restored histories are detectable.
- Recovery, confirmation, and verification decisions share one audit model.
- A future durable store must preserve append order and fingerprint chains.
- Checkpoint and durable Journal atomicity remains required before Journal can
  become the sole resume source.

## Principle

> Execution Journal does not store logs. It reconstructs, in time order, the
> decisions an Agent made.
