# Sprint 6 Draft: Memory, Artifact, and Dashboard Integration

Sprint 6 consumes the stable Runtime Gen1 and Sprint 5 reliability contracts.

Planned integration:

- Persist ArtifactRef values produced by verified node outputs.
- Index ExecutionSummary by GoalExecutionId, SnapshotId, and SessionId.
- Expose Timeline, AttemptHistory, waiting reason/since, verification status,
  retry/replan lineage, and recovery path to the Dashboard.
- Resolve follow-up references from verified artifacts without copying raw
  sensitive provider responses into diagnostics.
- Add retention and redaction policies for execution logs and artifacts.

Sprint 6 does not change NativeTaskGraph planning semantics or retry/replan
decisions.
