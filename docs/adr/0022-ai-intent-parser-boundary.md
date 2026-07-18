# ADR 0022 - AI Intent Parser Boundary

## Status

Accepted as the next architecture direction after Jarvis v0.6.0 Sprint 7.

## Context

Sprint 7 completed the Integration Bridge Foundation. The verified runtime path is:

```text
Planner -> Dispatcher -> Integration Ability -> Provider -> Result
```

The n8n Bridge contract, Mock Provider, `system.health`, `system.echo`,
permission handling, validation, provider capabilities, correlation IDs, retry
contract, and metrics are stable enough for the Sprint 7 boundary.

Remaining issues are mostly natural-language understanding issues. Voice input
can produce ambiguous phrases such as:

```text
n8n
system echo
external automation
```

or STT variants that are impractical to cover forever with regex aliases.

## Decision

Jarvis may add an AI Intent Parser / NLU layer before the Planner:

```text
STT
  |
User Vocabulary Correction
  |
AI Intent Parser
  |
Structured Intent
  |
Planner
  |
Dispatcher
  |
Ability
```

The AI Intent Parser is allowed to transform natural language into a structured
intent object, for example:

```json
{
  "intent": "integration.execute",
  "workflow_key": "notification.test",
  "payload": {
    "message": "테스트 메시지"
  }
}
```

The AI Intent Parser is not allowed to execute tools, call providers, bypass the
Registry, bypass Permission Layer checks, skip confirmation, or decide that a
result is valid.

## Rule

```text
AI structures intent.
Core validates and executes.
```

## Consequences

- Natural-language flexibility can improve without expanding regex aliases
  indefinitely.
- Permission and execution safety remain deterministic.
- Integration workflows remain fail-closed through the Workflow Registry.
- Confirmation-required actions still require the existing confirmation engine.
- Provider response validation remains outside the AI layer.

## Non-Goals

- No direct AI tool execution.
- No AI override of permissions.
- No hidden workflow execution.
- No replacement of Planner, Dispatcher, Ability Registry, or Provider
  validation.
