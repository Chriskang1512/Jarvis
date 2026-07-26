# Input And Wake Manager

Sprint 19 places a provider-driven Wake layer before normalized input.

```text
Microphone
  -> Wake audio capture
     -> Double Clap Detector
     -> Short Speech Segmenter
        -> Wake Phrase Transcriber
  -> Wake Manager
     -> Input Manager
     -> InputEnvelope
     -> Planner
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

Real-room calibration remains a device-level task. Double clap is enabled by
profile but Wake Word remains available as a fallback.

## Input Envelope

All future Voice, Keyboard, Clipboard, OCR, Image, File, Drag and Drop, Mobile,
and API inputs normalize to `InputEnvelope`.

The envelope contains source, modality, wake method, correlation metadata, and
a content fingerprint. `to_dict()` excludes raw content unless a caller
explicitly requests it. Raw input must not be written to operational logs.

## Runtime Contract

`WakeManager.wait_for_wake_word()` preserves the existing Voice Pipeline
interface. Tests may still use `WakeWordProvider.feed_text()` directly, but the
live provider receives text only from microphone wake transcription.
