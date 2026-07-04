# 0021 - Agent Runtime Architecture

## Status

Accepted

## Context

Beta.6 introduced Scheduler Foundation as a lifecycle layer for scheduled tasks.
Beta.7 introduces the first minimal Agent Runtime layer above Scheduler and the
Execution Kernel.

The main user pipeline remains separate:

```text
User
  |
Planner
  |
Execution Graph
  |
ExecutionRunner
  |
ResultMerge
  |
UnifiedResult
  |
Voice
```

The lifecycle path is:

```text
AgentRuntime
  |
Scheduler.due_tasks(now)
  |
Scheduler.trigger_due(now)
  |
ExecutionRunner.run_unified()
  |
UnifiedResult
```

AgentRuntime is not the executor. It is the Runtime Layer that manages the
lifecycle between Scheduler and the Execution Kernel.

Execution Kernel is Jarvis's common execution layer. It includes
ExecutionRunner and ResultMerger. Planner, Scheduler, and AgentRuntime call the
Execution Kernel to perform work. The Kernel returns `UnifiedResult`, the stable
execution interface for downstream layers.

```text
                User
                  |
                  v
             Planner
                  |
                  v
          Execution Graph
                  |
                  v
        Execution Kernel
        (Runner + Merge)
          |        |
          |        v
          |   UnifiedResult
          |        |
          |      Voice
          |
          v
      Scheduler
          ^
          |
    Agent Runtime
```

## Decision

Add `jarvis.agent_runtime` with:

- `AgentRuntime`
- `AgentRuntimeState`
- `AgentTickResult`
- `ExecutionKernel`
- runtime exceptions

`AgentRuntime` coordinates Scheduler and Execution Kernel through a manual
`tick(now)` method.

`ExecutionKernel` is a protocol requiring only `run_unified()`.

`AgentRuntime.start()` activates manual ticks.

`AgentRuntime.stop()` disables manual ticks.

`AgentRuntime.tick(now)` checks due tasks and asks Scheduler to trigger due work
using the injected Execution Kernel.

## Rules

AgentRuntime must not import Planner.

AgentRuntime must not import Voice.

AgentRuntime must not import Capabilities.

AgentRuntime must not execute plans directly.

AgentRuntime must not manage scheduled task state directly.

Scheduler owns schedule and task lifecycle.

Execution Kernel owns execution.

`UnifiedResult` remains the execution outcome.

## State Model

```text
STOPPED
IDLE
CHECKING
RUNNING
FAILED
```

## Out of Scope

- background thread
- asyncio loop
- daemon
- autonomous planning loop
- direct Planner calls
- direct Voice calls
- direct Capability calls
- Memory write loop
- automatic voice playback

## Consequences

- Beta.7 is a minimal runtime layer, not a fully autonomous agent.
- Future agent behavior can add loops around `tick()` without changing Scheduler
  lifecycle rules.
- Future Memory and Voice integration can consume runtime outcomes without being
  imported by AgentRuntime.
