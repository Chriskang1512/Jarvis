# Voice Architecture

Jarvis Voice Pipeline is a replaceable foundation for future voice features.

It runs separately from the existing CLI.

```text
python main.py       -> CLI
python voice_main.py -> Voice Pipeline
```

## Flow

```text
Wake
  |
STT
  |
LLM
  |
TTS
```

## Responsibilities

- Wake listens for the configured wake word.
- STT turns user speech into text.
- LLM uses the existing ChatService and ChatProvider architecture.
- TTS speaks the generated reply.

## STT Provider Configuration

Voice input is selected through config first:

```json
{
  "stt": {
    "provider": "openai",
    "language": "ko-KR",
    "device": "default",
    "openai_model": "gpt-4o-transcribe"
  }
}
```

Supported provider names:

- `mock`: terminal input fallback for deterministic smoke tests.
- `microphone`: local microphone input provider.
- `openai`: local microphone capture with OpenAI transcription.
- `hybrid`: Google/SpeechRecognition primary with OpenAI fallback for failures,
  short utterances, and confirmation turns. This remains available for A/B
  testing, but OpenAI is the v0.6 default.

`JARVIS_STT_PROVIDER` may override config for local smoke tests, but config is
the default source of truth.

Useful local overrides:

```text
JARVIS_STT_PROVIDER=openai
JARVIS_STT_OPENAI_MODEL=gpt-4o-transcribe
JARVIS_STT_OPENAI_LANGUAGE=ko
JARVIS_STT_FALLBACK_ENABLED=false
```

Sprint 12 introduces the STT v2 path:

```text
Audio Capture
  -> STT Provider
  -> Quality Gate
  -> Context-aware Correction
  -> Normalized Transcript
```

The v0.6 default is OpenAI-first STT. Google and hybrid providers remain
available for A/B testing and future provider switching, but the normal runtime
path uses `gpt-4o-transcribe` in accuracy-first mode unless configured otherwise.

Sprint 12 Phase 2 adds the formal STT result and measurement foundation:

- `TranscriptResult` captures provider, model, language, latency, fallback,
  correction, and error metadata.
- `TranscriptQualityGate` flags empty transcripts, provider failure text,
  unknown confirmations, and missing date/time signals.
- `STTMetrics` records request counts, success/failure/fallback/correction
  rates, confirmation failures, and average latency.
- Runtime startup shows `STT Fallback`, `Context Correct`, and `STT Metrics`.
- `scripts/stt_replay.py` can replay a saved WAV through STT providers so the
  same utterance can be compared without changing pronunciation, volume, or
  microphone distance.
- `scripts/stt_replay_corpus.py` runs the saved corpus across Google, OpenAI,
  and Hybrid providers, then writes exact/semantic match metrics to JSON.

Replay example:

```text
JARVIS_KEEP_STT_AUDIO=true
python scripts/stt_replay.py output/stt/sample.wav --providers openai
python scripts/stt_replay_corpus.py --providers google openai hybrid --repeat 10 --quiet
```

The replay command prints each transcript and a compact STT metrics console.

The correction and fallback layers are still transcription-only. They must not
infer new task content or bypass Planner, Dispatcher, or Permission checks.

Sprint 13 direction:

```text
Audio
  -> OpenAI STT
  -> Transcript Normalizer
  -> Known Entity Resolver
  -> Canonical Transcript
  -> Intent Parser
```

The replay corpus showed OpenAI as the best default provider, but it also showed
that near-miss transcripts such as "아야한테 일정 등록해" should be absorbed by
the semantic transcript layer before Intent parsing.

Still deferred:

- full `jarvis.voice.stt` provider split for Google/OpenAI/Hybrid classes,
- adaptive user-vocabulary learning candidates.

## Principle

Voice is an input/output layer.

Voice must not replace the Core.

Future providers can replace Wake, STT, and TTS without changing the CLI or ChatService contract.
