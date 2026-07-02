# ADR-0003: Voice Engine and Voice Personality Are Separate

## Status

Accepted

## Context

Jarvis will support multiple voice engines over time.

Examples include local TTS, OpenAI TTS, ElevenLabs, Windows SAPI, and future local voice models.

If Jarvis personality is tied directly to one voice engine, changing the engine can also change how Jarvis feels to the user.

## Decision

Voice Engine and Voice Personality are separate concepts.

Voice Engine decides which TTS technology speaks the response.

Voice Personality defines how Jarvis should sound and respond.

Examples of Voice Personality settings:

- tone
- speaking speed
- response length
- emotion expression
- user name or title
- formal or casual style

## Consequences

Jarvis can switch TTS engines without losing its voice identity.

Future voice providers should focus on audio generation.

Future voice personality settings should define Jarvis-like speech behavior independently from the selected engine.

This keeps Jarvis replaceable at the engine layer while preserving a consistent assistant identity.
