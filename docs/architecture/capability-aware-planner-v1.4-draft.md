# Capability-aware Planner v1.4 — Sprint 3 Draft

Sprint 3 maps a validated `GoalSpecification` plus a point-in-time Capability
Registry snapshot into a `NativeTaskGraph`. It does not execute the graph.

## Planner input

- GoalSpecification and SemanticContext
- Capability Registry snapshot
- Supported operation input/output schemas
- Permission requirements that cannot be downgraded
- GraphExecutionPolicy limits
- Existing ExecutionPlan for shadow comparison

## Planner output

- NativeTaskGraph JSON schema v1.0
- Planning confidence and diagnostics
- Missing-input/clarification result instead of invented values
- Repair response accepting structured ValidationIssue values

## Required invariants

- Only registered capability/operation pairs may be emitted.
- All required inputs are bound using supported BindingSourceType values.
- NodeOutput bindings name a real typed output.
- Permission levels are copied from the registry.
- Restricted operations never become automatic nodes.
- The planner cannot emit execution state.

## Repair loop

`Plan -> NativeTaskGraphValidator -> ValidationReport -> Repair -> Validate`

Repair is bounded. It receives issue codes and field paths and changes only the
invalid plan definition. Capability Registry validation and permission
validation are added as separate stages so structural errors remain
deterministic and provider-independent.

## Shadow comparison

Until NativeTaskGraph planning is promoted, compare it with the existing
ExecutionPlan on capability selection, order, missing steps, permission level,
bindings, expected outputs, and planner failure reasons. No NativeTaskGraph is
executed in Sprint 3.
