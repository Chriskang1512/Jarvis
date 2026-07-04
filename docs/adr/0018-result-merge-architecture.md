# 0018 - Result Merge Architecture

## Status

Accepted

## Context

Beta.1 introduced Planner, Beta.2 introduced Execution Graph, and Beta.3
introduced Capability Context. After a graph runs, each capability still returns
an independent result. Voice and UI should not need to understand internal
execution details to answer the user.

## Decision

Add a Result Merge layer after Execution Graph.

The layer receives completed capability results only and returns one
`UnifiedResult` contract:

```json
{
  "summary": "3 capabilities completed",
  "results": [],
  "warnings": [],
  "errors": [],
  "metadata": {}
}
```

`ResultMerger` is a provider-style interface:

```python
class ResultMerger(Protocol):
    def merge(self, results: list, metadata: dict | None = None) -> UnifiedResult:
        ...
```

`DefaultResultMerger` is the first deterministic implementation. Future AI
Merge, Priority Merge, and Streaming Merge implementations can replace it.

`UnifiedResult` is frozen after merge. Merge output should be treated as a final
response object for downstream layers.

## Rules

Result Merge must not plan.

Result Merge must not execute tools.

Result Merge must not read Memory.

Result Merge must not call capabilities.

Result Merge only organizes already produced results.

Result Merge must not be embedded inside `ExecutionRunResult`.

## Merge Rules

Success and completed statuses are added to `results`.

Warning statuses are added to `warnings`.

Failed and error statuses are added to `errors`.

Embedded warnings in successful result payloads are promoted to `warnings`.

Execution metadata is preserved, including execution ID, plan ID, elapsed time,
node count, completed node count, failed node count, timestamp, and per-node
timing.

## Integration

`ExecutionGraphRunner.run()` keeps returning raw ordered execution results for
backward compatibility.

`ExecutionGraphRunner.run_unified()` executes the graph and passes
`ExecutionRunResult.results` plus metadata to the configured `ResultMerger`.

The flow remains:

```text
ExecutionRunResult
  |
ResultMerger
  |
UnifiedResult
```

```text
Planner
  |
Execution Graph
  |
Capabilities
  |
Result Merge
  |
UnifiedResult
```

Voice can read `UnifiedResult.summary`.

UI can render `results`, `warnings`, `errors`, and `metadata`.

## Consequences

- Voice integration can consume one stable object in Beta.5.
- UI layers can show both the natural summary and detailed execution metadata.
- Future implementations can replace `DefaultResultMerger` with Simple Merge,
  Priority Merge, LLM Merge, or AI Merge without changing the execution layer.
