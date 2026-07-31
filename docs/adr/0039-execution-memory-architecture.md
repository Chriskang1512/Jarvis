# ADR 0039: Execution Memory Architecture

Status: Accepted

## Context

Jarvis v1.4 produces immutable `ExecutionSummary` values, but those values
were not retained as searchable execution experience. Re-delivery after a
restart or event replay can also deliver the same summary more than once.
Persisting raw execution state would leak provider responses and user data.

## Decision

Jarvis v1.5 Sprint 1 introduces a separate Execution Memory boundary:

```text
ExecutionSummary
→ MemoryRedactor
→ ExecutionMemoryRecord
→ ExecutionMemoryRepository
→ MemoryIndexer
→ MemorySearch
```

- `ExecutionSummary` remains immutable and is never modified for storage.
- Records carry independent schema and summary versions.
- `(sourceExecutionId, summaryVersion)` is the idempotency key.
- The redactor runs before repository persistence. Persistence is default-deny:
  only explicitly allow-listed fields are copied, so newly added
  `ExecutionSummary` fields cannot enter memory automatically.
- Provenance and confidence are separate contracts.
- Session replay stores a checkpoint/journal reference, not copied events.
- SQLite and in-memory repositories implement the same provider-neutral API.
- Semantic search is behind a replaceable provider interface.
- `PlannerHint` is defined as a contract only. No Planner runtime receives it
  during Sprint 1.

## Privacy boundary

Tokens, secrets, passwords, mail bodies, attachments, contact details, raw
tool input/output, transcripts, and approval audio are excluded or redacted.
Search results expose provenance and verification status.

Memory persistence failure emits `execution_memory.persist.failure` with
structured identifiers and an error type. It never changes a successful
execution outcome, but it is never silently discarded.

## Permission history boundary

Permission history stores only the decision state (`requested`, `approved`,
or `denied`), scope, timestamp, and a non-sensitive reason. A past approval
is audit evidence only. It is never evidence for automatically approving a
current or future execution.

## SQLite schema migration

SQLite repositories maintain an `execution_memory_schema_versions` table.
Initialization runs ordered migrations inside a transaction. An unsupported
future database version or an inconsistent existing schema fails fast rather
than opening the repository with an ambiguous layout.

## Consequences

Execution completion can safely accumulate searchable history without
changing Planner or GraphExecutor decisions. Ranking, Planner injection,
graph reuse, and lifecycle enforcement remain disabled until their planned
v1.5 sprints.
