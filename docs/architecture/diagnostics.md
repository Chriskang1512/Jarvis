# Diagnostics Architecture

Jarvis Diagnostics is a developer tool for understanding runtime state.

It is not a user interface.

## Flow

```text
Publisher
  |
Collector
  |
Snapshot
  |
Console
```

## Responsibilities

- Publishers are Jarvis modules such as Voice, Memory, Tool Calling, Finance, Calendar, and Automation.
- Collector aggregates metadata and is the source of truth.
- Snapshot is the versioned diagnostics data contract.
- Console renders the snapshot as plain text.

## Principle

Modules publish metadata.

Diagnostics collects metadata.

Console renders metadata.

The console must not become the source of truth.
