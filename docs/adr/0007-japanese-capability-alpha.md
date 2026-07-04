# 0007 - Japanese Capability Alpha

## Status

Accepted

## Context

Jarvis v0.4 Sprint 2 introduced Capability Plugins as the primary extension
unit. Sprint 3 needs the first real capability without modifying Brain Core.

Japanese learning is a good first capability because it can start with safe,
local, deterministic tools and does not require an external API.

## Decision

Implement Japanese Capability Alpha inside `jarvis.capabilities.japanese`.

The capability is structured as a small application:

```text
japanese/
  __init__.py
  metadata.py
  tools/
    translate.py
    grammar.py
    reply.py
    review.py
  prompts/
    translate.md
    grammar.md
    reply.md
  tests/
```

The capability owns four SAFE tools:

- `japanese_translate`
- `japanese_grammar`
- `japanese_reply`
- `japanese_review`

Each tool exposes ToolMetadata with `capability="japanese"`, aliases, supported
intents, examples, SAFE permission metadata, and route confidence. The Brain
Tool Router continues to work only from ToolRegistry metadata.

`japanese_review` may use MemoryManager when available. If memory has no
Japanese expressions, it returns fallback study guidance.

## Consequences

- Brain remains unchanged.
- Japanese tools are registered through Capability Registry into ToolRegistry.
- PermissionLayer still authorizes tool execution.
- Dispatcher still owns execution.
- This is not a full JLPT curriculum, speech/shadowing system, or spaced
  repetition engine.
