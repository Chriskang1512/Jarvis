# v0.4 Alpha Architecture Review

## Status

Reviewed after Finance Capability Alpha.

## 1. Brain Independence

Result: Pass for the v0.4 Capability path.

`BrainToolRouter` does not import Japanese, Finance, or any capability module. It
only iterates over ToolRegistry entries and reads ToolMetadata.

Known note: `jarvis.brain.controller` is a legacy agent keyword router and still
contains older agent names such as Japanese. That path is separate from the new
Capability -> ToolRegistry -> BrainToolRouter path and should be retired or
renamed in a later cleanup.

## 2. Capability Independence

Result: Pass.

Japanese and Finance do not import each other. Each capability owns its metadata,
tools, prompts, and local tests folder.

## 3. Tool Metadata

Result: Strengthened.

Current routing metadata:

- `capability`
- `aliases`
- `supported_intents`
- `examples`
- `route_confidence`
- `safety_level`
- `version`
- `priority`
- `deprecated`

The review added `version`, `priority`, and `deprecated` for tool-level lifecycle
and routing control.

## 4. Router Score

Result: Good for alpha, intentionally simple.

Current scoring:

- Exact alias or supported intent match: `1.0`
- Exact example match: `0.98`
- Metadata prefix match: `0.95`
- Arithmetic expression special case for calculator tools
- Candidate must pass each tool's `route_confidence`
- Score ties are broken by `ToolMetadata.priority`
- Deprecated tools are skipped

Future work: add token/semantic matching after more real prompts accumulate.

## 5. Capability Lifecycle

Result: Alpha-ready.

`CapabilityRegistry` supports:

- install/register
- enable
- disable
- remove
- upgrade
- lookup
- enabled listing

Disabled capabilities do not register tools into ToolRegistry, so Brain has no
candidate to route.

## 6. Startup

Result: Acceptable for alpha.

Startup flow:

```text
CapabilityLoader
  |
CapabilityRegistry
  |
ToolRegistry
  |
BrainToolRouter
```

Capability discovery uses local `pkgutil.iter_modules` and imports installed
capability packages once during startup. Startup time and memory are currently
small because capabilities are local and deterministic.

Future work:

- explicit reload API for long-running app sessions
- startup timing diagnostics
- optional lazy tool construction if capability count grows

## 7. Test Coverage

Result: Improved.

The suite now covers feature behavior and architecture behavior:

- Brain routes only through ToolRegistry metadata
- disabled capability produces no router candidate
- deprecated tool is skipped
- priority breaks score ties
- capability duplicate rejection
- capability enable/disable/remove/upgrade lifecycle
- Japanese and Finance regressions
- Core calculator/time/diagnostics regressions

## Review Summary

The v0.4 alpha architecture is ready for the next capability after one note:
legacy Brain agent routing should not be used as the model for new capabilities.
New domains should follow the Capability app structure and expose tools through
metadata only.

## Final Addendum

Result: Ready for v0.4 Alpha platform freeze.

The final capability set is:

- Japanese
- Finance
- Creator
- Hotel
- Life

Consistency checklist:

- Capability folder layout consistency: all five concrete capabilities include
  `metadata.py`, `tools/`, `prompts/`, and `tests/`.
- Metadata consistency: all five capabilities expose version, status, owner, and
  tool lists through `CapabilityMetadata`.
- Output contract consistency: each tool returns structured `ToolResult`
  payloads. Life reflection and reminder now expose planner/scheduler-readable
  contracts.
- Prompt asset structure: each concrete capability has prompt assets under its
  own `prompts/` folder.
- Tool registration: all capability tools register through
  `CapabilityRegistry.register_tools()` into the shared `ToolRegistry`.
- Router metadata quality: capability tools expose aliases, supported intents,
  examples, safety level, route confidence, version, priority, and deprecation
  metadata.
- Version/status/owner fields: concrete capabilities are marked alpha and owned
  by Jarvis Team.
- Tests: full regression suite covers capability discovery, registration,
  routing, output contracts, lifecycle behavior, and core route regressions.
- Documentation: README, overview, roadmap, changelog, architecture review, and
  ADRs describe the v0.4 capability platform.
- ADR numbering: historical ADR numbering contains earlier duplicate prefixes
  and a reserved gap, but v0.4 platform ADRs are explicit:
  `0005` Brain Tool Router, `0006` Capability Plugin Framework, `0007`
  Japanese, `0008` Finance, `0010` Creator, `0011` Hotel, `0012` Memory
  Ownership Rule, and `0013` Life.

Memory ownership rule:

```text
Only Memory owns Memory.
Capabilities never own Memory.
Capabilities access Memory only through approved interfaces.
Dependency Injection only.
No direct coupling.
```

Capability philosophy:

```text
Brain decides.
Capability specializes.
Tool executes.
Memory remembers.
Permission protects.
Dispatcher delivers.
```
