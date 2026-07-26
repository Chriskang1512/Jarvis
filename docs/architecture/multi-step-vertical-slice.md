# Multi-step Vertical Slice

Sprint 18.7 validates the Agent Core as one execution path rather than adding a
new provider feature.

## Runtime Contract

```text
Goal
  -> Planner / Discovery
  -> Validator / Optimizer
  -> RuntimeTask
  -> Calendar.create
  -> Reminder.create
  -> Mail.send (WAIT_CONFIRM)
  -> Confirm or Cancel
  -> Verification
  -> Result / Execution Journal
```

One goal creates one `RuntimeTask`. A confirmation boundary freezes the plan,
resolved context, prior step results, current task snapshot, and next safe step
in `PendingPlanExecution`. `confirm_task(task_id)` executes that exact frozen
step with `_confirmed`; it does not parse the user's goal or rebuild the draft.

`cancel_task(task_id)` cancels only the pending branch. Side effects completed
before the confirmation boundary remain completed and Mail is not called.

## Resume Boundary

`InMemoryPendingExecutionStore` is the default development store. The store and
`TaskStateMachine` are injectable, so a recreated Runtime can restore the same
Task and checkpoint. A production process-restart store must protect draft
payloads at rest; plain JSON persistence of recipients or Mail bodies is not an
acceptable implementation.

Resume always consumes a `RecoveryDecision`. Runtime restores the checkpoint,
validates it through the State Machine, and resumes at the frozen step. Runtime
does not infer retry count, strategy, or resume mode.

## Verification And Compensation

Providers may return a successful transport result that fails Runtime
verification. A tool with an explicit `rollback(input_data, tool_result)`
contract is compensated in that case. Runtime records `ROLLBACK_COMPLETED` or
`ROLLBACK_UNAVAILABLE` without storing provider payloads.

Rollback is opt-in. Runtime never guesses a destructive compensation.

## Journal Proof

The vertical slice requires the same Task journal to contain Goal, Plan,
Discovery, Validation, Optimization, Permission, Execution, Verification, and
Result phases. Replay verifies the fingerprint chain and ordered step records.
Explain uses dependency reasons recorded during capability selection.

## Ownership Rule

Conversation state belongs to `RuntimeTask`, never to an Ability. Draft
artifacts exist only in `ConversationContext` while the Task is waiting and are
removed at terminal completion or cancellation.
