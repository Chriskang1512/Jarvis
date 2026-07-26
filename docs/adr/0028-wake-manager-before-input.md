# ADR 0028: Wake Manager Before Input Manager

## Status

Accepted

## Decision

Wake is a separate policy and provider layer before Input Manager. Clap, Voice,
Keyboard, Touch Portal, Mobile, API, and future BLE triggers emit `WakeEvent`.
Input Manager converts subsequent content into `InputEnvelope`; Planner never
depends on a wake implementation.

Clap detection operates on audio signal features before STT. Wake capture stops
before command transcription begins.

## Consequences

- Users can enable and order wake methods through a profile.
- New trigger transports do not change Planner or Voice Pipeline.
- Clap audio avoids STT cost and is not persisted.
- Global hotkey and remote listener permissions remain in platform adapters.
- Wake Word remains a fallback while device-specific Clap thresholds mature.
