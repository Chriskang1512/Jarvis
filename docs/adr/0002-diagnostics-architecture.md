# ADR-0002: Diagnostics Architecture

## Status

Accepted

## Context

Jarvis is growing into a modular assistant platform.

Future modules such as Voice, Tool Calling, Memory, Finance, Calendar, Browser, and Automation need a shared way to publish runtime metadata.

Diagnostics must help developers understand the current state of Jarvis without coupling modules directly to a console, GUI, or web dashboard.

## Decision

Diagnostics uses `DiagnosticsCollector` as the source of truth.

Modules publish metadata into the collector.

The console renders a `DiagnosticSnapshot` from the collector.

The console must not become the source of truth.

```text
Modules
  |
DiagnosticsCollector
  |
DiagnosticSnapshot
  |
DiagnosticsConsole
```

## Consequences

Future modules should publish diagnostics metadata through collector methods.

Examples:

- Voice publishes wake, STT, TTS, and pipeline status.
- Tool Calling publishes tool start, finish, and failure metadata.
- Memory publishes memory operation metadata.
- Finance publishes finance operation metadata.
- Calendar publishes calendar operation metadata.

Future renderers such as CLI, GUI, Electron, Web Dashboard, or Mobile should read snapshots instead of talking directly to modules.

When new metadata categories are added, `DiagnosticSnapshot.version` may be increased to keep compatibility clear.
