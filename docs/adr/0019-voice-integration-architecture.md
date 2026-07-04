# 0019 - Voice Integration Architecture

## Status

Accepted

## Context

Beta.4 introduced `UnifiedResult`, a single merged response object for Voice and
UI. Beta.5 connects that object to the Voice layer without exposing Voice to
Planner, Execution Graph, or Capability internals.

The project already has older STT/TTS pipeline code. Beta.5 adds a narrower
contract for orchestration output:

```text
UnifiedResult
  |
VoiceService
  |
VoiceProvider
  |
VoiceResult
```

## Decision

Voice depends only on `UnifiedResult` shape.

`VoiceService.speak(response)` reads `response.summary`.

`VoiceService` delegates synthesis to an injected `VoiceProvider`.

`VoiceProvider.synthesize(text)` returns a `VoiceResult`.

`MockVoiceProvider` is the only implemented provider in Beta.5.

`OpenAIVoiceProvider` is reserved as a placeholder for a future release.

Audio playback is out of scope for Beta.5.

## Contract

```python
class VoiceProvider(Protocol):
    def synthesize(self, text: str) -> VoiceResult:
        ...
```

```python
@dataclass(frozen=True)
class VoiceResult:
    text: str
    audio: bytes | None
    provider: str
    duration_ms: int
    metadata: dict
```

## Rules

Voice must not import Planner.

Voice must not import Execution Graph.

Voice must not import Capabilities.

Voice must not inspect `UnifiedResult.results`, `warnings`, `errors`, or
`metadata` for speech text.

Voice must not play audio in Beta.5.

Voice providers are replaceable through dependency injection.

## Future

Future providers may include OpenAI, Azure, ElevenLabs, Google, and local engines.

Future streaming TTS should extend the provider contract without changing
Planner, Execution, or Result Merge.

Audio playback should be a separate layer after voice synthesis so platform
dependencies such as PyAudio, sounddevice, or OS audio APIs do not leak into the
VoiceService contract.
