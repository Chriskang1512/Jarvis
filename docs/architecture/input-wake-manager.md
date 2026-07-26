# Input And Wake Manager

Sprint 19 places a provider-driven Wake layer before normalized input.

```text
Voice / Keyboard / Clipboard / Future Inputs
  -> InputProvider
  -> InputManager
  -> InputEnvelope
     -> InputContext
        -> ActivationContext
  -> Intent Parser
  -> Planner

Microphone / Hotkey / External Trigger
  -> WakeManager
  -> ActivationContext
  -> InputManager
```

## Wake Providers

`WakeManager` accepts providers with a common `poll()` contract and selects the
first event allowed by `WakeProfile` priority:

1. Double clap
2. Voice wake phrase
3. Keyboard hotkey
4. Touch Portal
5. Mobile
6. API

Methods are independently enabled. BLE can be added without changing Planner
or Voice Pipeline.

The live Voice entry point opens one shared `sounddevice` stream only while
waiting for wake. The stream feeds both the double-clap detector and a short
speech segmenter, then closes before command STT opens the microphone.

Voice wake accepts spoken `자비스`, `헤이 자비스`, and `hey jarvis`.
Only a short speech candidate is transcribed, and only an exact configured
phrase creates a Wake event. There is no `Wake word >` console listener in the
live runtime. Clap audio is rejected by minimum speech duration and is never
sent to STT or stored.

The current keyboard, Touch Portal, Mobile, and API providers are trigger
boundaries. Platform-specific global hotkey and network listeners remain
separate adapters; they call `trigger()` and do not bypass Wake policy.

## Clap Safety

`ClapDetector` requires:

- a peak and RMS above configurable thresholds;
- a high crest factor to reject sustained speech or music;
- a refractory interval to avoid counting one impulse twice;
- a minimum and maximum interval between the two impulses.
- a short settle window after the second impulse; a fast third impulse cancels
  the pending double-clap activation.

One clap never activates Jarvis. Three rapid claps are rejected instead of
activating on the first two. Real-room calibration remains a device-level task.
The Wake profile supports `clap_peak_threshold`, `clap_rms_threshold`,
`clap_crest_factor_threshold`, `clap_min_gap_seconds`,
`clap_max_gap_seconds`, and `clap_settle_seconds`.

## Runtime Hardening

- Wake capture stops immediately after one provider wins. It remains stopped
  during command STT, TTS playback, and Follow-up Listening, preventing TTS
  self-activation.
- Pending events from simultaneous providers are cleared before the next Wake
  session, so Clap and Voice cannot cause a duplicate activation.
- Follow-up speech belongs to the active conversation and does not require or
  consume a new Wake event.
- `voice.input.envelope` Trace contains only source, modality, activation
  provenance, content length, and fingerprint. It never contains raw input.

## Input Envelope

Voice, Keyboard, and Clipboard inputs plus OCR, Image, File, Mobile, and API
provider boundaries normalize through `InputManager.ingest()` into an immutable
`InputEnvelope`. The console keyboard path and every Voice turn, including
follow-up and confirmation speech, use this same gate.

The envelope contains source, modality, input type, correlation context,
typed metadata, and a content fingerprint. `to_dict()` excludes raw content
unless a caller explicitly requests it. Raw input must not be written to
operational logs.

`ActivationContext` generalizes how Jarvis was activated:

```text
activation_type
activation_provider
activation_phrase
activated_at
confidence
activation_id
```

Wake Word, double clap, hotkey, and external triggers therefore share one
Planner-independent contract. The legacy `wake_method` and `wake_provider`
fields remain readable during migration but are derived compatibility data.

## Input Providers

`InputProvider.read()` returns provider-neutral `ProviderInput`. Keyboard and
Clipboard use queue adapters today; platform callbacks submit content without
calling Planner directly. OCR, Image, File, and Mobile adapters are explicit
stubs with stable source and modality declarations.

## Runtime Contract

`WakeManager.wait_for_wake_word()` preserves the existing Voice Pipeline
interface. Tests may still use `WakeWordProvider.feed_text()` directly, but the
live provider receives text only from microphone wake transcription.
