# ADR Index

This index records the current architecture decision documents for Jarvis.

Note: early ADRs contain duplicate numeric prefixes from older parallel
architecture tracks. New v0.4 orchestration ADRs continue from 0014 onward.

## v0.4 Orchestration ADRs

- 0014 - Intent Planner Contract
- 0015 - Planner Layer Rule
- 0016 - Execution Runner Rule
- 0017 - Execution Context Rule
- 0018 - Result Merge Architecture
- 0019 - Voice Integration Architecture
- 0020 - Scheduler Foundation Architecture
- 0021 - Agent Runtime Architecture
- 0022 - AI Intent Parser Boundary
- 0023 - Google Workspace Cross-Ability Context
- 0024 - Agent Core Integration
- 0025 - Capability Lifecycle Status (Proposed)

## Sprint 18 Agent Core

ADR 0024 defines the integration direction for the existing Planner,
Ability Registry, Permission Layer, RuntimeTask, conversation state, checkpoint
resume contract, and Execution Journal.

ADR 0025 records the proposed `Experimental -> Stable -> Deprecated -> Sunset`
capability lifecycle and its privacy-safe Telemetry boundary. It does not
change runtime behavior yet.

## Release Candidate Review

ADR 0018 through ADR 0021 are accepted and align with v0.4.0-rc.1:

- Result Merge returns `UnifiedResult`.
- Voice consumes `UnifiedResult.summary`.
- Scheduler models task lifecycle and calls the Execution Kernel.
- Agent Runtime coordinates Scheduler and Execution Kernel lifecycle.
