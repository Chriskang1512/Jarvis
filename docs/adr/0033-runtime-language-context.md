# ADR 0033: Runtime Language Context

- Status: Accepted
- Date: 2026-07-28

## Decision

Language is a turn-scoped runtime concern represented by one `LanguageContext`.
STT language detection and response language are intentionally separate.

```text
Input -> STT -> LanguageResolver -> Planner/Ability -> Response normalization
      -> language-selected TTS
```

`LanguageContext` records detected language, response language, policy,
detection confidence, STT provider, and selected TTS voice. It is attached to
`RuntimeTurn`, returned to Dashboard clients, and published through
`runtime.language.resolved`.

Supported policies are `AUTO`, `FORCE_KO`, `FORCE_JA`, and `FORCE_EN`. AUTO
follows the detected input language unless an explicit request or a
conversation-scoped preference selects another response language. A forced
policy remains authoritative.

Planner and Ability inputs always receive the original transcript. Language
instructions never alter rule matching. A final response that does not match
the resolved non-Korean language is translated while preserving facts and
formatting. TTS voice selection is temporary and restored after each call.

OpenAI STT receives no language hint in AUTO mode so it can detect multilingual
audio. Wake-word transcription remains a separate, constrained lifecycle.
