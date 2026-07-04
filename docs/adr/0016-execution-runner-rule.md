# 0016 - Execution Runner Rule

## Status

Accepted

## Context

v0.4 Beta.1 introduced the Intent Planner Contract. Beta.2 introduces the first
runtime that can execute validated capability plans.

Because the Runner sits near routing and execution, it must stay narrow. If it
starts planning, validating, merging, or choosing tools directly, Jarvis loses
the separation created by the Capability Platform.

## Decision

Runner only walks validated execution graphs.

Runner never creates plans.

Runner never modifies plans.

Runner never validates plans.

Runner never merges outputs.

Runner delegates all routing and execution.

## Execution Runner Philosophy

```text
Runner executes.
Runner never plans.
Runner never validates.
Runner never selects capabilities.
Runner never selects tools.
Runner delegates routing.
Runner delegates authorization.
Runner delegates execution.
```

## Consequences

- Planner remains responsible for plans.
- Plan Validator remains responsible for validation.
- Capability Router remains responsible for routing capability intents.
- Permission and Dispatcher remain responsible for authorization and execution.
- Beta.2 returns ordered node results only. Result Merge remains future work.

## Future

Runner Events should become structured event objects for future subscribers:

```json
{
  "type": "node_started",
  "node": "life_001"
}
```

Future Voice, GUI, WebSocket, and Dashboard surfaces should subscribe to these
events instead of parsing text logs.

Execution results reserve `execution_id` so the same plan can be executed more
than once and still be tracked separately.
