# ADR 0034: Goal and Semantic Context Architecture

Status: Accepted
Date: 2026-07-28

## Context

Jarvis v1.4 introduces goal-oriented execution while preserving the existing
direct ability path. A planner cannot reliably create an executable graph from
raw conversation text alone. Follow-up references, temporal expressions,
preferences, and previous provider results must first be normalized with their
origin and confidence.

## Decision

The pipeline boundary is:

`Natural Language -> SemanticContext -> GoalSpecification -> Request Router`

`SemanticContext` contains domain, typed slots, entity references, temporal and
language context, an optional previous result, confidence, and per-value
provenance. `ConversationContextEngine` stores context per session and merges
values using this strict precedence:

1. Explicit input
2. Explicit control command
3. Current-turn entity
4. Conversation context
5. User preference
6. System default

Stored state is isolated by `ContextKey(UserId, ConversationId, SessionId)` and
retained as bounded turn records. The engine is an injected instance, not a
process-global singleton. A new conversation cannot see ordinary entities or
previous results from another conversation.

Provenance is a structured value containing source, turn id, parser id, source
field, capture time, and confidence. Conversation-inherited slots and entities
decay on each turn and expire below the configured confidence threshold.
`ContextLifecycle` records creation/reference timestamps, conversation scope,
turn-window expiration, decay factor, and turn index.

The initial policy values (`max_turns=12`, `confidence_decay=0.90`, and
`min_confidence=0.35`) are constructor configuration, not protocol constants.
They may be tuned from production measurements without changing serialized
SemanticContext or GoalSpecification contracts.

`GoalParser` consumes the existing rule/AI intent parser contract. It converts
successful structured intents into goal context, preserves AI structured
output, and performs deterministic semantic extraction when the AI parser is
disabled or fails. It also classifies the request as `direct` or
`goal_oriented`; it does not execute an ability or graph.

Routing uses explicit planning signals: multiple capabilities, result
dependencies, conditional branches, external state changes, previous-result
dependencies, and pause/resume requirements. Conjunctions alone do not promote
a request. Sprint 3's planner will validate the classification again.

Previous provider results can carry existing runtime `ArtifactRef` values.
References such as “아까 그 일정” attach that result to the new context without
copying provider-specific objects into the domain model.

## Compatibility

This module is additive. Existing Ability, Provider, Permission, and Direct
Execution behavior remains unchanged. Runtime adoption can happen behind the
request router or in shadow mode. Weather's string-enrichment compatibility
path can later be removed after callers consume typed semantic slots.

## Consequences

- Planner inputs are deterministic and explainable.
- Explicit user input cannot silently lose to a stored preference.
- Follow-up requests normalize into the same model as first-turn requests.
- Session persistence is currently an injected in-memory concern; durable
  storage can be added without changing the domain contract.
- Sprint 2 can define `NativeTaskGraph` bindings against typed context slots and
  previous artifacts rather than interpolated strings.
