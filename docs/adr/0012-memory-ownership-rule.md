# 0012 - Memory Ownership Rule

## Status

Accepted

## Context

Life Capability is closer to Memory than previous capabilities. Future
capabilities and planners will also need memory context. Without a strict
ownership rule, capabilities could become directly coupled to Memory internals.

## Decision

Only Memory owns Memory.

Capabilities never own Memory.

Capabilities access Memory only through approved interfaces.

Dependency Injection only.

No direct coupling.

## Consequences

- Memory remains Core-owned.
- Capabilities may receive approved Memory interfaces from runtime wiring.
- Capabilities must not import storage internals or create their own Memory
  stores.
- Future Planner and Scheduler work must follow the same rule.
