# 0001 - Event-driven Architecture

## Status

Accepted

## Context

Jarvis will grow into a system with Core, Agents, Memory, Automation, Voice, and future visual renderers.

If these parts call each other directly, the project will become hard to maintain.

## Decision

Jarvis will use an event-driven architecture.

The Core publishes events to an EventBus. Other modules subscribe to the events they need.

The Core does not know who consumes the events.

## Consequences

- Core stays UI-independent.
- Agents, Memory, Automation, and renderers can evolve separately.
- Future renderers such as Rive, Electron, and Unity can be added without rewriting Core logic.

## Notes

Rive is not Jarvis's brain. Rive is a face that reacts to JarvisState events.
