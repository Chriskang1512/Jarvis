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

## Principle

Voice is an input/output layer.

Voice must not replace the Core.

Future providers can replace Wake, STT, and TTS without changing the CLI or ChatService contract.
