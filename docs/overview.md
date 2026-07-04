# Jarvis Project Overview

Jarvis is a Python-based personal AI assistant project.

The first version is a local CLI chat program. The user types a command, the Brain analyzes it, and the Brain sends the command to a specialized Agent.

## Main Parts

- Brain: Main controller that decides what should happen.
- Brain Tool Router: Registry-driven router that chooses SAFE tools before LLM chat.
- Agents: Small workers that handle specialized jobs.
- Memory: Simple storage for conversation and task history.
- Config: Basic project settings.
- Logs: Place for future execution logs.
- Docs: Project notes and explanations.

## First Development Goal

The first goal is not to build every AI feature at once. The first goal is to create a clean structure that can grow safely.

## v0.4 Tool Routing

```text
User
  |
Voice / Text
  |
Brain
  |
Brain Tool Router
  |
  |--------------------|
  |                    |
Tool Route            LLM Route
  |                    |
Permission            Chat
  |
Dispatcher
  |
Tool
```

The router discovers tools from `ToolRegistry` and uses `ToolMetadata` to score
candidate routes. It does not execute tools directly. It only returns a
`ToolRequest`; the existing `PermissionLayer` and `ToolDispatcher` keep their
v0.3 responsibilities.

## v0.4 Beta Intent Planner

Beta starts Capability Orchestration. The Intent Planner decomposes one user
goal into capability-level tasks, but it does not execute them.

```text
User
  |
Brain
  |
Intent Planner
  |
Capability Plan
  |
Plan Validator
  |
Capability Router
  |
Tool
  |
Permission
  |
Dispatcher
```

Detailed planning boundary:

```text
Brain
  |
Intent Planner
  |
Capability
  |
Intent
  |
Capability Router
  |
Tool
```

The planner knows capabilities and intents. It never knows tools.

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

Beta.1 always marks execution as sequential and does not merge outputs.

Plan validation is reserved before execution:

```text
Planner
  |
Plan Validator
  |
Execution
```

## v0.4 Beta Execution Graph Runtime

Beta.2 introduces the Execution Layer.

```text
User
  |
Brain
  |
Intent Planner
  |
Plan Validator
  |
Execution Graph Runner
  |
Capability Router
  |
Permission
  |
Dispatcher
  |
Tool Result
```

Runner walks validated plans sequentially. It does not plan, validate, choose
capabilities, choose tools, access Memory, or merge outputs.

Runner returns ordered node results:

```json
{
  "execution_id": "exec_xxx",
  "plan_id": "plan_xxx",
  "status": "completed",
  "results": []
}
```

## v0.4 Beta Capability Context

Beta.3 adds temporary execution context.

```text
Node
  |
Input Resolve
  |
Execute
  |
Store Result
  |
Next Node
```

Execution Context is owned by Runner and destroyed after execution. It is not
Memory.

Context contract:

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

Tool input contract:

```json
{
  "user_input": "",
  "previous_results": [],
  "execution_snapshot": {}
}
```

`ExecutionInputData` is append-only. Existing fields remain backward compatible,
and capabilities should ignore unknown fields.

Runner always preserves this update order:

```text
Execute
  |
Result
  |
Context Update
  |
Next Node
```

## v0.4 Capability Plugins

```text
Capability
  |
Tool
  |
Permission
  |
Dispatcher
```

Capabilities group related tools into independent extension modules. The
Capability Registry discovers enabled capabilities and registers their tools
into the shared Tool Registry. Brain remains unaware of individual capabilities.

## Japanese Capability Alpha

Japanese is the first concrete capability. It registers four SAFE tools:

- `japanese_translate`
- `japanese_grammar`
- `japanese_reply`
- `japanese_review`

These tools are normal ToolRegistry entries. Brain routes to them by metadata;
PermissionLayer and ToolDispatcher keep the same Core responsibilities.

Japanese also sets the internal structure pattern for larger capabilities:
metadata lives at capability level, tools live in separate modules, prompt
templates live under `prompts/`, and future capability-local tests can live
under `tests/`.

## Finance Capability Alpha

Finance is the second concrete capability. It registers four SAFE tools:

- `finance_compound`
- `finance_average_price`
- `finance_profit`
- `finance_exchange`
- `finance_portfolio`

Finance proves that a different domain can join the same platform without
modifying Brain, Router, Registry, Permission, or Dispatcher.

## Creator Capability Alpha

Creator is the third concrete capability and the first creative engine. It
registers five SAFE tools:

- `creator_lyrics`
- `creator_music_prompt`
- `creator_title`
- `creator_description`
- `creator_song_package`

Prompts are first-class assets under `prompts/`. Creator outputs are structured
so future planners can compose lyrics, music prompts, titles, descriptions, tags,
and thumbnail prompts without tool-specific parsing.

Creator is also the first capability designed with sub-domains. Song is active
now; Video, Blog, and Presentation are reserved. Creator assets carry
`project`, `subdomain`, and `asset` fields to support future Project -> Assets
-> Output workflows.

## Hotel Capability Alpha

Hotel is the fourth concrete capability and Jarvis's hospitality operations
assistant. It registers three SAFE tools:

- `hotel_schedule_planner`
- `hotel_complaint_report`
- `hotel_complaint_manual`

The schedule planner returns draft schedules, conflicts, and notes rather than a
perfect optimizer. Complaint tools return structured manager reports and SOP
guidance for front office workflows.

## Life Capability Alpha

Life is the fifth concrete capability and the final v0.4 alpha capability. It is
closer to Memory than the previous capabilities, but it still follows the same
platform path and does not modify Brain or Core.

It registers five SAFE tools:

- `life_todo`
- `life_reminder`
- `life_routine`
- `life_habit`
- `life_reflection`

`life_reflection` summarizes a day or sprint into summary, wins, problems,
ideas, and next actions. It can read recent Memory when a MemoryManager is
provided, but Memory remains Core-owned.

`life_reminder` does not create real reservations in alpha. It returns a
Scheduler-ready payload with `message`, `recommended_time`, and
`priority`, and `ready_for_scheduler`.

## Capability Philosophy

```text
Brain decides.
Capability specializes.
Tool executes.
Memory remembers.
Permission protects.
Dispatcher delivers.
```

## Planner Philosophy

```text
Brain decides if planning is required.
Planner decomposes goals.
Planner knows capabilities.
Capabilities own their tools.
Permission authorizes.
Dispatcher executes.
Merge returns one response.
```

## Planner Design Rules

```text
1. Planner never knows tools.
2. Planner plans at capability level.
3. Planner never touches Memory.
4. Planner never touches Dispatcher.
5. Planner never bypasses Permission.
6. Planner outputs executable capability tasks only.
7. Planner produces a stable planning contract.
8. Execution remains sequential in Beta.1.
```

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

## Execution Context Philosophy

```text
Execution Context is temporary.
Execution Context belongs to the Runner.
Capabilities never own execution context.
Capabilities receive immutable execution snapshots.
Capabilities never mutate execution context.
Runner is the only owner of execution state.
Execution Context is destroyed after execution.
Memory remains long-term storage.
```
