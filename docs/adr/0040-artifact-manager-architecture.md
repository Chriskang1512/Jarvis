# ADR 0040: Provider-neutral Artifact Manager Architecture

Status: Accepted

## Context

Jarvis execution outputs previously used provider objects or small artifact
dictionaries. Those representations cannot support stable cross-provider search,
relationships, lifecycle management, replay, or future SDK contracts.

## Decision

Jarvis v1.5 Sprint 2 introduces one provider-neutral artifact boundary:

```text
Verified Node Output
→ ArtifactBuilder
→ ArtifactRef
→ ArtifactRepository
→ ArtifactIndexer
→ Artifact Search / Dashboard
```

- Only `ArtifactBuilder` creates new `ArtifactRef` values.
- IDs are deterministic and stable for an execution/node/output/resource identity.
- Checksums are required. Binary and text content use SHA-256/content hashes;
  Provider resources retain both their external resource ID and checksum.
- `ArtifactRef` is immutable and versioned; lifecycle and relationship updates
  create replacement values with the same ID.
- Provider identity is provenance, never the artifact's domain type.
- Repository and metadata search contracts are provider-independent.
- Native Graph outputs declared with `artifact_type` are captured after
  verification. Raw provider payloads are not stored in artifact metadata.
- The older `jarvis.runtime.task.ArtifactRef` remains a direct-execution
  compatibility projection. `jarvis.artifacts.ArtifactRef` is the canonical
  v1.5 platform contract; compatibility removal requires a separate migration.
- Artifact persistence failure emits `artifact_manager.persist.failure` and
  does not change the execution outcome.
- Semantic search is an extension interface only and is not Runtime-enabled.
- The Dashboard reads artifact summaries, counts, provenance, and relationships.

## Relationships and lifecycle

Parent/child relationships form an acyclic tree. Repositories reject self-links,
missing references, cycles, and paths deeper than the configurable default of
20 levels. Lifecycle states are `Created`, `Updated`,
`Archived`, and `Deleted`; deletion is soft by default.

SQLite persistence uses an ordered `SQLiteArtifactMigrationRunner`, a dedicated
schema-version table, post-migration schema validation, and fail-fast handling
for unknown future versions or inconsistent layouts.

## Access boundary

Visibility is explicitly one of `Private`, `Session`, `User`, or `System`.
The default is `Private`. Artifact references carry only metadata, hashes,
external resource identifiers, and URIs. Content remains under its owning
Provider or file store access policy.

## Consequences

Memory, Dashboard, future Planner hints, SDKs, Plugins, Mobile, and GUI surfaces
can share one artifact language. Existing direct execution remains compatible;
Planner injection, embeddings, RAG, and Plugin SDK behavior remain out of scope.
