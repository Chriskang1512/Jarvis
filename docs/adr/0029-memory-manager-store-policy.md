# ADR 0029: Memory Manager And Store Policy

## Status

Accepted

## Context

Jarvis already has a conversation context, a legacy key/value MemoryService,
a JSON Memory Ability, and a general JSON Memory Store. Replacing them in one
migration would risk existing user data and unrelated Workspace behavior.

Persistent memory also creates a product risk: storing every user sentence
produces noise, privacy problems, and unreliable Planner context.

## Decision

`jarvis.memory.MemoryManager` is the new structured Memory entry point.
Persistence is defined by `MemoryRepository`, with `SQLiteMemoryProvider` as
the default local implementation.

Existing Memory APIs remain compatible during migration. RuntimeTask continues
to own pending conversational state.

All automatic durable writes pass through `MemoryStorePolicy`. Unknown and
ephemeral statements fail closed. Post-execution updates require a successful
Ability result.

Planner retrieval is read-only. Retrieved memory can influence execution only
through operation-specific allowlists; raw MemoryContext is never attached to
Plan or Journal payloads.

Memory lifecycle changes publish `MemoryStored`, `MemoryUpdated`,
`MemoryDeleted`, `MemoryRetrieved`, and preference-specific
`PreferenceChanged` through Core EventBus. Events expose fingerprints,
timestamps, and provenance metadata, never raw values or user utterances.

Memory provenance is explicit: source channel, source provider, creator, and a
bounded confidence score are part of the record contract. Working Memory has a
default 30-minute TTL and is also cleared when its owning runtime session ends.
SQLite schema additions use in-place additive migration for existing users.

## Consequences

- SQLite becomes the replaceable structured Repository without forcing a
  rewrite of the existing Memory Ability.
- Working, long-term, and preference memory share one record contract while
  retaining different lifecycle rules.
- Personal Lexicon, Correction Memory, Entity Graph, and Cloud Memory are
  explicit extension points, not partial implementations.
- Store Policy must grow through reviewed rules and tests rather than generic
  transcript capture.
- Dashboard, Metrics, History, Audit, and future Sync can consume Memory
  lifecycle events without coupling to SQLite.
- Working Memory cleanup is deterministic across both timeout and normal
  runtime shutdown paths.
- Legacy JSON migration can be performed incrementally in a later sprint.
