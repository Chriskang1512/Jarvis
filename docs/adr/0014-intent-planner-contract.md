# 0014 - Intent Planner Contract

## Status

Accepted

## Context

v0.4 Alpha made Jarvis a Capability Platform with Japanese, Finance, Creator,
Hotel, and Life. v0.4 Beta begins Capability Orchestration.

The first Beta step is not multi-tool execution. It is a stable planning
contract that can safely describe cross-capability work.

## Decision

Introduce an Intent Planner that plans at capability level.

The Planner may output:

```json
{
  "capability": "finance",
  "intent": "compound simulation"
}
```

The Planner must not output:

```json
{
  "tool": "finance_compound"
}
```

Planner contract:

```json
{
  "plan_id": "plan_xxx",
  "planner_version": "0.1",
  "graph_version": "1.0",
  "goal": "",
  "status": "CREATED",
  "requires_planning": true,
  "permission_mode": "SAFE",
  "execution_mode": "sequential",
  "graph": {
    "nodes": [
      {
        "id": "finance_001",
        "step": 1,
        "capability": "finance",
        "intent": "compound simulation",
        "input": "VOO를 20년 적립",
        "status": "CREATED",
        "required": true,
        "confidence": 0.82
      }
    ],
    "edges": [
      {
        "id": "edge_001",
        "from": "finance_001",
        "to": "jp_002",
        "type": "sequential"
      }
    ],
    "metadata": {}
  }
}
```

## Planner Design Rules

1. Planner never knows tools.
2. Planner plans at capability level.
3. Planner never touches Memory.
4. Planner never touches Dispatcher.
5. Planner never bypasses Permission.
6. Planner outputs executable capability tasks only.
7. Planner produces a stable planning contract.
8. Execution remains sequential in Beta.1.

## Consequences

- Planner reads `CapabilityRegistry` and capability metadata only.
- Planner does not import or call `ToolRegistry`.
- Planner does not call Dispatcher.
- Planner does not access Memory.
- Planner marks `permission_mode` but does not bypass Permission.
- Planner marks new plans as `CREATED` in Beta.1.
- Planner marks new nodes as `CREATED` in Beta.1.
- Planner uses `graph_version` to version graph structure separately from
  planner behavior.
- Graph edges reserve stable IDs for future parallel, merge, retry, and
  diagnostic behavior.
- Execution Graph reserves `metadata` for future estimates such as cost,
  tokens, and time.
- Plan nodes reserve `required` and `confidence` for future execution and
  fallback policy.
- Plan validation can reject plans that reference missing capabilities before
  execution begins.
- Execution Graph, Capability Context, Result Merge, Voice integration,
  Scheduler integration, and Agent behavior remain future Beta work.
