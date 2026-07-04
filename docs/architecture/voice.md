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
    "provider": "mock",
    "language": "ko-KR",
    "device": "default",
    "openai_model": "gpt-4o-mini-transcribe"
  }
}
```

Supported provider names:

- `mock`: terminal input fallback for deterministic smoke tests.
- `microphone`: local microphone input provider.
- `openai`: reserved provider name for a future OpenAI STT implementation.

`JARVIS_STT_PROVIDER` may override config for local smoke tests, but config is
the default source of truth.

Next sprint should harden the microphone provider around device selection,
ambient-noise calibration, timeout handling, and clear fallback errors.

## Principle

Voice is an input/output layer.

Voice must not replace the Core.

Future providers can replace Wake, STT, and TTS without changing the CLI or ChatService contract.
