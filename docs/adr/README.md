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

## Release Candidate Review

ADR 0018 through ADR 0021 are accepted and align with v0.4.0-rc.1:

- Result Merge returns `UnifiedResult`.
- Voice consumes `UnifiedResult.summary`.
- Scheduler models task lifecycle and calls the Execution Kernel.
- Agent Runtime coordinates Scheduler and Execution Kernel lifecycle.
