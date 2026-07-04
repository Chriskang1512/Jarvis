# 0017 - Execution Context Rule

## Status

Accepted

## Context

Beta.2 executes validated graphs sequentially. Beta.3 must let later nodes use
earlier node results without confusing temporary execution data with long-term
Memory.

## Decision

Execution Context exists only during execution.

Execution Context is not Memory.

Execution Context is created by Runner.

Execution Context is destroyed after Runner finishes.

Runner may read and write Execution Context.

Capabilities never import or own Execution Context.

Capabilities receive immutable execution snapshots.

Capabilities never mutate execution context.

Runner is the only owner of execution state.

Capabilities remain input-output units. Runner injects resolved context into
tool input.

## Contract

```json
{
  "context_version": "1.0",
  "execution_id": "exec_xxx",
  "values": {
    "finance_001": {
      "result": {}
    }
  }
}
```

## InputData

Capabilities receive context through a stable input contract:

```json
{
  "user_input": "",
  "previous_results": [],
  "execution_snapshot": {}
}
```

The `execution_snapshot` value is read-only. Capabilities may read it but must
not mutate it.

`ExecutionInputData` is append-only.

Existing fields must remain backward compatible.

Capabilities should ignore unknown fields.

Future fields such as `user_profile`, `voice_context`, `scheduler_context`, and
`agent_context` may be added without breaking existing capabilities.

## Context Update Rule

Runner must always preserve this order:

```text
Execute
  |
Result
  |
Context Update
  |
Next Node
```

## Consequences

- Memory remains long-term storage.
- Execution Context is per-run temporary data.
- Execution Context reserves `context_version` for future migration.
- Sequential nodes can consume previous node results.
- Capabilities receive immutable snapshots and cannot update execution state.
- Context is destroyed after execution and is not persisted.
- Parallel execution, merge, retry, scheduler, and agent behavior remain future
  Beta work.
