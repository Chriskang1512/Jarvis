# Agent Core Gap Analysis and Migration Design

## Purpose

Sprint 18.0 compares the current Jarvis runtime with the target Agent Core.
This sprint changes contracts and ownership before adding new behavior.

Architecture principle:

> AI turns a goal into a plan. Core validates, optimizes, executes, and
> remembers that plan.

## Target Flow

```text
Goal
  -> Plan
  -> Schema Validation
  -> Dependency Validation
  -> Plan Optimization
  -> Permission Evaluation
  -> Runtime Task
  -> Step Execution and Validation
  -> Checkpoint / Confirmation / Retry
  -> Verification
  -> Execution Journal
  -> Final Result
```

## Current-to-Target Mapping

| Area | Current implementation | Decision | Sprint 18 target |
| --- | --- | --- | --- |
| Runtime planning | `RuntimePlanner`, `ExecutionPlan`, `ExecutionStep`, AI intent adapter | EXTEND / MIGRATE | Versioned goal and plan contracts with validation and optimization stages |
| Legacy planning | `jarvis.planner` capability-level graph contract | DEPRECATE after migration | Preserve useful capability-first rules, remove the parallel execution contract |
| Ability registry | `AbilityRegistry` with capability index | REUSE / EXTEND | Registry is the source for capabilities, schemas, permissions, side effects, validators, and verifiers |
| Tool registry adapter | `AbilityToolAdapter`, `ToolRegistry`, `RuntimeToolRegistry` | REUSE / MIGRATE | Keep execution adapter; Planner resolves capabilities without depending on tool names |
| Ability metadata | capability list and input/output schema already exist | EXTEND | Normalize schemas and add operation-level metadata |
| Permission layer | safe/confirm/restricted and `_confirmed` boolean | MIGRATE | Signed/versioned permission snapshot bound to task, step, input fingerprint, and expiry |
| Runtime task | state, current step, completed/failed IDs, retry count and records | REUSE / EXTEND | Durable task aggregate with pause/resume, checkpoint version, plan version, artifacts, and journal sequence |
| Task runner | sequential execution, retries, cancellation, limited validation | REUSE / EXTEND | Dependency-aware execution with validators/verifiers around every step and checkpoint boundaries |
| Step context | ad hoc `last_calendar_event` and `last_contact` dictionaries | MIGRATE | Typed output bindings validated against Registry schemas |
| Confirmation | Voice Session `pending_action` dictionary containing plan/input | MIGRATE | Runtime Task owns confirmation request and immutable draft reference |
| Conversation clarification | Voice Session pending dicts and Calendar-specific conversation task | DEPRECATE / MIGRATE | Generic Conversation Resolver updates a Runtime Task; Ability remains stateless |
| Mail context | mutable `MailAbility.last_messages` and `last_selected_message` | MIGRATE | Session/Task-owned selection context passed explicitly to Mail Ability |
| Retry | synchronous retry count and delay inside TaskRunner | EXTEND | Retry policy, attempt journal, retryable classification, checkpoint before another attempt |
| Resume | Voice reconstructs continuation from plan, index, and prior results | DEPRECATE / MIGRATE | Checkpoint restoration plus external-operation verification |
| Task history | bounded in-memory snapshots | REUSE as cache | Durable Execution Journal is authoritative; TaskHistory becomes a read cache |
| EventBus | synchronous in-memory fan-out | REUSE / EXTEND | Publish lifecycle events after journal append; never use EventBus as durable truth |
| Diagnostics/metrics | trace events, aggregate intent metrics, provider timings | REUSE | Derive operational metrics from journal/event data without storing sensitive payloads |
| Provider metadata | provider/service/action/scopes/trace IDs | EXTEND | Add operation ID, idempotency support, side-effect class, and verification capability |

## Confirmed Gaps

### Plan Contract

- `ExecutionStep` identifies `tool_name`, not a Registry capability operation.
- Inputs and outputs are dictionaries without schema-bound bindings.
- `depends_on` exists, but cycle, missing dependency, and compatibility checks do
  not run as a formal pre-execution stage.
- Rule-specific reorder logic is embedded in Planner/Dispatcher functions.
- There is no plan version or optimizer decision record.

### Task and Resume

- Every `TaskRunner.run()` creates a new task ID, including confirmation
  continuation.
- Completed steps and context can be passed back in, but no durable checkpoint
  owns them.
- Retry is immediate and does not verify whether a timed-out external operation
  already succeeded.
- `WAIT_EXTERNAL` exists but has no complete transition or persistence contract.
- `PAUSED`, `RESUMING`, and `RETRYING` are not modeled.

### Conversation Ownership

- `ConversationSession` owns `pending_action`, `pending_clarification`, and a
  Calendar-only conversation task.
- Voice reconstructs executable inputs and injects `_confirmed`.
- Mail Ability keeps recent-message and selected-message state internally.
- These paths prevent stateless Ability execution and durable cross-session
  resume.

### Journal and Privacy

- TaskHistory is process-local and bounded.
- Task records contain response and error text but not plan versions,
  permission snapshots, external operation IDs, artifacts, or checkpoints.
- Trace output is useful telemetry, but is neither ordered nor durable enough to
  reconstruct a task.
- No single redaction policy governs task inputs, artifacts, and journal events.

## Ownership Boundaries

| Component | Owns | Must not own |
| --- | --- | --- |
| AI Intent Parser | Goal interpretation and proposed plan | Execution, permission approval, optimization authority |
| Planner | Plan construction from goal and Registry metadata | Provider calls or mutable conversation state |
| Validator | Schema, dependency, capability, and policy validation | User intent changes |
| Optimizer | Semantics-preserving plan ordering and deduplication | New goals, weaker permissions, or new side effects |
| Runtime Task | State, checkpoint, confirmation, attempts, artifacts | Provider-specific objects |
| Conversation Resolver | Mapping user turns to task commands or missing fields | Ability-owned pending state |
| Ability | Stateless domain operation | Session state, confirmation state, orchestration |
| Provider | External API translation and verification | Planner or conversation decisions |
| Execution Journal | Ordered durable task facts | Raw secrets or full sensitive payloads |

## Migration Sequence

1. Introduce versioned Goal, Plan, Step, binding, and validation result models
   alongside current `ExecutionPlan`.
2. Add Registry operation metadata and schema normalization without changing
   Ability execution.
3. Add Plan Validator, then a no-op Plan Optimizer with an auditable interface.
4. Extend RuntimeTask states and introduce checkpoint storage.
5. Bind confirmation and permission snapshots to task/step/fingerprint.
6. Move Voice pending dictionaries into RuntimeTask projections.
7. Move Calendar conversation collection into the generic Conversation
   Resolver.
8. Move Mail selection context out of Mail Ability.
9. Introduce the durable Execution Journal and rebuild TaskHistory as a
   projection.
10. Migrate the Calendar -> Reminder -> Mail vertical slice.
11. Remove legacy continuation and Ability-owned state only after parity tests.

## Initial Impact Files

| Phase | Primary files |
| --- | --- |
| 18.1 contracts | `jarvis/runtime/planner/plan.py`, `step.py`, new goal/validation/optimizer modules |
| Registry metadata | `jarvis/abilities/metadata.py`, `registry.py`, `adapter.py`, Ability manifests |
| Task states | `jarvis/runtime/task/models.py`, `runner.py`, `history.py` |
| Checkpoints | new `jarvis/runtime/task/checkpoint.py`, storage interface and implementations |
| Permissions | `jarvis/permissions/models.py`, `layer.py` |
| Conversation migration | `jarvis/voice/conversation.py`, `pipeline.py`, `jarvis/runtime/conversation_task.py` |
| Stateless Mail | `jarvis/abilities/native/mail/ability.py`, query/result contracts |
| Journal | new `jarvis/runtime/journal` package, EventBus adapters, diagnostics projection |

## Sprint 18.0 Exit Criteria

- The five architecture documents and Agent Core ADR agree on names and states.
- Current components are classified as REUSE, EXTEND/MIGRATE, or DEPRECATE.
- Checkpoint and journal schemas contain no provider objects or raw secrets.
- Resume defaults to verification when side effects are uncertain.
- The 18.1 implementation order and affected files are explicit.
