# 0015 - Planner Layer Rule

## Status

Accepted

## Context

The Intent Planner starts v0.4 Beta Capability Orchestration. Because the
Planner sits between Brain and capabilities, it could accidentally grow into a
new Core or a direct tool executor if its boundary is not explicit.

## Decision

Planner is not Core.

Planner is not Capability.

Planner consumes only Capability metadata.

Planner never imports ToolRegistry.

Planner never executes.

Planner only creates executable plans.

## Consequences

- Planner may inspect `CapabilityRegistry` and `CapabilityMetadata`.
- Planner must not instantiate concrete capabilities.
- Planner must not import concrete capability packages such as Finance,
  Japanese, Creator, Hotel, or Life.
- Planner must not import or call ToolRegistry, Dispatcher, or Memory.
- Capability-specific routing remains inside capabilities and future
  capability routers.
