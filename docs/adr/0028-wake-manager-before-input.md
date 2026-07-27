# ADR 0028: Wake Manager Before Input Manager

## Status

Accepted

## Decision

Wake is a separate policy and provider layer before Input Manager. Clap, Voice,
Keyboard, Touch Portal, Mobile, API, and future BLE triggers emit `WakeEvent`.
Input Manager converts subsequent content into `InputEnvelope`; Planner never
depends on a wake implementation.

Activation details belong to typed `ActivationContext`, not loose Wake Word
fields on Input data. It records activation type, provider, phrase, timestamp,
confidence, and event ID. The envelope may expose legacy Wake fields only as
compatibility projections.

Every initial command, follow-up, and confirmation turn must pass through
`InputManager`. Input Providers produce data; they never dispatch Planner or
Ability calls directly.

Clap detection operates on audio signal features before STT. Wake capture stops
before command transcription begins.

## Consequences

- Users can enable and order wake methods through a profile.
- New trigger transports do not change Planner or Voice Pipeline.
- Clap audio avoids STT cost and is not persisted.
- Global hotkey and remote listener permissions remain in platform adapters.
- Wake Word remains a fallback while device-specific Clap thresholds mature.
- Keyboard and Clipboard input can evolve independently from Keyboard and
  external Wake triggers.
- Wake monitoring is inactive during STT, TTS, and Follow-up execution.
- A short post-pattern settle window rejects rapid triple claps, and all
  losing-provider events are discarded after one provider activates Runtime.
- Per-device calibration must accept exactly two clap candidates per trial;
  incomplete trials retry and cannot silently weaken the resulting profile.
- Sprint 19.2 owns the completed integration, diagnostics, calibration, and
  regression scope. A separate Sprint 19.3 integration phase is unnecessary.
- Environmental detection cannot be universally perfect. A measured
  door-close near-match is accepted as a documented residual risk because it
  produced no activation in the target room; real false activations trigger
  recalibration or policy tuning.
