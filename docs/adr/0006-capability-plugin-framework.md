# 0006 - Capability Plugin Framework

## Status

Accepted

## Context

Jarvis v0.4 Sprint 1 made Brain capable of selecting SAFE tools through
ToolRegistry metadata. The next step is to make related tools installable and
maintainable as independent capability modules.

Future capabilities such as Finance, Japanese, Hotel, Creator, and Life should
not require Brain changes when they add tools.

## Decision

Introduce a `jarvis.capabilities` framework.

- `CapabilityMetadata` describes each capability.
- Capability metadata includes version, status, and owner so capabilities can
  mature independently.
- `CapabilityRegistry` stores capabilities, rejects duplicate IDs, exposes
  lookup APIs, and registers enabled capability tools into ToolRegistry.
- `CapabilityLoader` discovers installed capability packages automatically by
  looking for `create_capability`.
- Initial skeletons exist for Creator, Finance, Hotel, Japanese, and Life.

The existing Tool Registry, Permission Layer, Dispatcher, Plugin System, and
Brain Tool Router remain in place.

## Consequences

- Capability owns tools.
- Tool owns metadata.
- Permission owns authorization.
- Dispatcher owns execution.
- Brain owns decision making only.
- Business logic remains outside this sprint and can be added capability by
  capability.
