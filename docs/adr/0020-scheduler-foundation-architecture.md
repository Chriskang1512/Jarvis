# 0020 - Scheduler Foundation Architecture

## Status

Accepted

## Context

Beta.1 through Beta.5 created a synchronous pipeline:

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
  |
VoiceService
  |
VoiceResult
```

Beta.6 starts the scheduling foundation. The goal is not to create a background
runtime. The goal is to model scheduled task lifecycle so future agent runtime
work can ask for due tasks and execute them predictably.

Beta.6의 목표는 시간을 흐르게 만드는 것이 아니라, 예약 Task의 Lifecycle을
모델링하는 것이다.

## Decision

Add a `jarvis.scheduler` package with model, service, store, clock, and exception
boundaries.

The model flow is:

```text
ScheduleRequest
  |
Schedule
  |
ScheduledTask
  |
TaskState
  |
Scheduler
  |
due_tasks(now)
  |
ExecutionRunner.run_unified()
  |
UnifiedResult
```

Beta.6 supports one-shot schedules only through `Schedule.run_at`.

`TaskState` is an enum:

```text
PENDING
READY
RUNNING
COMPLETED
FAILED
CANCELLED
```

`Scheduler` is a protocol with:

```python
def schedule(request): ...
def get(task_id): ...
def list(): ...
def cancel(task_id): ...
def due_tasks(now): ...
```

`InMemoryScheduler` is the default implementation.

`InMemoryTaskStore` is the default storage implementation.

`SystemClock` and `FixedClock` provide clock abstraction for runtime and tests.

## Due Rule

`ScheduledTask.is_due(now)` returns true only when:

```text
state in {PENDING, READY}
and schedule.run_at <= now
```

`CANCELLED`, `RUNNING`, `COMPLETED`, and `FAILED` tasks are never due.

## Trigger Rule

Beta.6 supports manual triggering only:

```text
trigger_due(now)
  |
due_tasks(now)
  |
RUNNING
  |
ExecutionRunner.run_unified()
  |
COMPLETED or FAILED
```

Failures are isolated per task. One failed task must not stop later due tasks.

## Boundaries

Scheduler does not know Planner.

Scheduler does not know Voice.

Scheduler does not know Capabilities.

Scheduler executes only through an injected object that provides
`run_unified()`.

Scheduler receives `UnifiedResult` as the execution outcome.

## Out of Scope

- background thread
- asyncio loop
- cron parser
- recurring schedule
- interval schedule
- conditional schedule
- OS scheduler
- Windows Scheduler
- background daemon
- real notification delivery
- automatic voice playback

## Consequences

- Beta.6 is Scheduler Foundation, not Scheduler Engine.
- Future SQLite, Redis, or Cloud schedulers can replace `InMemoryScheduler`.
- Beta.7 Agent Runtime can build a loop around Scheduler without changing task
  lifecycle rules.
