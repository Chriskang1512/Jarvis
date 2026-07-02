# ADR-0001: Core Never Knows Vendors

## Status

Accepted

## Reason

Jarvis Core must not depend on a specific AI vendor.

If Core knows names such as OpenAI, Claude, Gemini, or Anthropic, every new provider can force changes in core layers.

That would make Jarvis harder to maintain and harder to extend.

## Decision

Only `ProviderFactory` knows which vendor provider is selected.

Core layers must stay vendor-agnostic:

- `ChatCommand`
- `ChatService`
- `PromptBuilder`
- `EventBus`
- `MemoryService`

Provider-specific code belongs in Provider implementations and `ProviderFactory`.

## Consequences

When adding a new Provider, Core must not be modified.

Allowed extension points:

- Provider
- ProviderFactory
- Configuration
- Documentation

This keeps Jarvis modular and makes future providers replaceable by configuration.
