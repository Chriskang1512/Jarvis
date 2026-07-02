# 0003 - Visual Adapter

## Status

Accepted

## Context

Jarvis may later have visual interfaces such as Console, Rive, Electron, or Unity.

The visual layer should not control Jarvis Core.

## Decision

Visual renderers will be treated as adapters.

They consume JarvisState events from the EventBus and translate them into visual changes.

## Consequences

- Rive can map JarvisStatus values to state machine inputs.
- Console can print state changes during development.
- Electron and Unity can be added later without changing Core.

## Notes

Expected mapping:

```text
idle -> idle
wake -> wake
listening -> listening
thinking -> thinking
speaking -> speaking
working -> working
success -> success
error -> error
```
