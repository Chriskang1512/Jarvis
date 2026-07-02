# 0002 - Provider Abstraction

## Status

Proposed

## Context

Jarvis may use different AI providers in the future, such as OpenAI, Claude, local models, or MCP-based tools.

Directly coupling Jarvis Core to one provider would make future changes harder.

## Decision

Jarvis should use a provider-agnostic AI layer.

The Core should ask for a capability, not a specific provider.

## Consequences

- OpenAI can be added first without blocking future providers.
- Claude, local models, and MCP tools can be added later.
- Tests can use fake providers without calling real APIs.

## Notes

API keys and secrets must never be committed to GitHub.
