# ADR 0024 - Agent Core Integration

## Status

Accepted for Sprint 18.

## Context

Jarvis already has an Ability Registry, Permission Layer, Runtime Planner,
multi-step ExecutionPlan, RuntimeTask, retry handling, confirmation follow-up,
EventBus, provider abstractions, and task history.

Those capabilities evolved through multiple vertical slices. Planning contracts
are duplicated, conversation state is partly owned by Voice and Ability
instances, task history is in-memory, and confirmation continuation is rebuilt
from dictionaries rather than a durable checkpoint.

Sprint 18 must integrate these parts without replacing proven provider and
Ability boundaries.

## Decision

Jarvis adopts this Agent Core flow:

```text
Goal
  -> Plan
  -> Validate
  -> Optimize
  -> Permission
  -> Runtime Task
  -> Execute and Validate Each Step
  -> Checkpoint / Confirm / Retry / Resume
  -> Verify
  -> Execution Journal
  -> Final Result
```

Architecture principle:

> AI turns a goal into a plan. Core validates, optimizes, executes, and
> remembers that plan.

## Planner and Registry

- Planner operates on Registry capability operations and schemas.
- AI may propose a plan but cannot validate, optimize, authorize, or execute it.
- Ability Registry becomes the source of capability, input/output schema,
  permission, side-effect, retry, idempotency, validator, and verifier metadata.
- Tool adapters remain an execution detail.

## Optimizer Invariant

> The Optimizer may change order, but it must not change the user's goal,
> permissions, or side effects.

Core rejects an optimized plan when its semantic fingerprint differs from the
validated input plan.

## Task Ownership

- Runtime Task owns state, confirmation, clarification requirements,
  checkpoints, attempts, artifacts, and resume policy.
- Conversation Session references the active task and presents questions.
- Ability execution is stateless and receives all required context explicitly.
- Provider-specific objects never leave Provider boundaries.

## Pause and Resume

- `PAUSED` is valid only after a checkpoint is durably saved.
- `RESUMING` restores the checkpoint, verifies external execution, recomputes
  input fingerprints, validates confirmation/draft versions, and re-evaluates
  permissions.
- `RUNNING` is re-entered only after resume validation succeeds.
- Unknown external outcomes become `UNKNOWN_SIDE_EFFECT`.
- Unknown side effects are verified first and never automatically re-executed.
- If verification remains inconclusive, Jarvis requests user clarification.

## Execution Journal

- The Journal is append-only and authoritative for task reconstruction.
- TaskHistory, metrics, resumable tasks, and user summaries are projections.
- State changes are journaled before EventBus publication.
- Journal payloads use normalized IDs, hashes, masked fields, and protected
  artifact references instead of secrets or raw provider responses.

## Migration

The migration is incremental:

1. Add versioned contracts and adapters.
2. Extend Registry metadata.
3. Add validation and a no-op auditable optimizer.
4. Extend RuntimeTask and add checkpoint storage.
5. Add Execution Journal mirroring.
6. Move confirmation and conversation state into RuntimeTask.
7. Make stateful Abilities stateless.
8. Migrate the Calendar -> Reminder -> Mail vertical slice.
9. Remove legacy planners and Voice continuation paths after parity tests.

## Consequences

- Existing integrations remain usable during migration.
- Plan and task versions add storage and compatibility responsibilities.
- External writes become safer to resume but require provider verification
  contracts.
- Voice becomes a client of Agent Core rather than the owner of execution
  state.
- New integrations can compose through Registry schemas instead of
  Planner-specific code.

## Related Documents

- `docs/architecture/agent-core-gap-analysis.md`
- `docs/architecture/planner-contract.md`
- `docs/architecture/task-state-machine.md`
- `docs/architecture/checkpoint-resume-contract.md`
- `docs/architecture/execution-journal.md`
