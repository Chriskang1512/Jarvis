# 0013 - Life Capability Alpha

## Status

Accepted

## Context

Jarvis v0.4 now has Japanese, Finance, Creator, and Hotel capabilities. The
remaining v0.4 alpha capability is Life.

Life is different from previous capabilities because it is closer to Memory and
daily continuity. It should help with todos, reminders, routines, habits, and
reflections without taking ownership of Core Memory.

## Decision

Implement Life Capability Alpha inside `jarvis.capabilities.life`.

Life owns five SAFE tools:

- `life_todo`
- `life_reminder`
- `life_routine`
- `life_habit`
- `life_reflection`

`life_reflection` returns a planner-readable contract:

```json
{
  "summary": "",
  "wins": [],
  "problems": [],
  "ideas": [],
  "next_actions": [],
  "memory_used": true
}
```

It may read recent memories through an injected `MemoryManager`, but Memory
remains Core-owned.

`life_reminder` does not create real scheduled jobs. It returns a payload that a
future Scheduler can consume:

```json
{
  "message": "...",
  "recommended_time": "tomorrow morning",
  "priority": "normal",
  "ready_for_scheduler": true
}
```

## Consequences

- Life completes the v0.4 alpha capability set.
- Jarvis now has five independent capability applications.
- Life becomes a natural bridge toward v0.5 Capability Collaboration.
- Scheduler execution, real calendar writes, and automatic habit persistence
  remain non-goals for this alpha.
