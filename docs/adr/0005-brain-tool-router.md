# 0005 - Brain Tool Router

## Status

Accepted

## Context

Jarvis v0.3 built the Core platform: Tool Registry, Dispatcher, Permission
Layer, Plugin System, Diagnostics, Memory, Conversation, and Voice. v0.4 should
make that Core useful without redesigning it.

The first capability layer needs to decide whether a user request should become
a safe tool call or continue to normal LLM chat.

## Decision

Add a Brain Tool Router before the normal Chat/LLM path.

The router is metadata-driven:

- `ToolRegistry` describes available tools.
- `ToolMetadata` provides route hints such as capability, aliases, supported
  intents, input mode, input prefixes, and route confidence.
- `PermissionLayer` authorizes automatic routing.
- `ToolDispatcher` owns execution.

The Brain Tool Router only selects a route and returns a `ToolRequest`. It does
not execute tools and does not contain business logic.

Only SAFE tools are eligible for automatic routing in v0.4 Phase 1.

## Consequences

- Existing v0.3 Core responsibilities remain intact.
- New SAFE tools can be registered without changing Brain routing code.
- Future capability plugins can expose tools through metadata and reuse the same
  route path.
- Confirm and restricted tool routing remain future work.
