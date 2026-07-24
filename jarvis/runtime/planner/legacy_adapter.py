from jarvis.runtime.planner.contracts import AgentPlan, GoalEnvelope, PlanStep


def adapt_execution_plan(execution_plan, conversation_id="", source="legacy_runtime"):
    """Map the current tool-oriented plan into the Agent Core contract."""
    goal = GoalEnvelope(
        normalized_goal=execution_plan.raw_text.strip(),
        requested_outcomes=tuple(
            f"{step.tool_name}.{step.action}" if step.action else step.tool_name
            for step in execution_plan.steps
        ),
        conversation_id=conversation_id,
        source=source,
        raw_text_ref=f"legacy:{execution_plan.id}",
    )
    step_ids = {step.index: f"STEP-{step.index}" for step in execution_plan.steps}
    steps = tuple(
        PlanStep(
            step_id=step_ids[step.index],
            ordinal=step.index,
            capability=step.tool_name,
            operation=step.action,
            input=dict(step.input_data),
            depends_on=tuple(step_ids[index] for index in step.depends_on if index in step_ids),
            side_effect=_side_effect(step.action),
            permission=_permission(step.action),
            verification_policy="provider_result" if _side_effect(step.action) != "none" else "none",
            idempotency_policy="legacy_runtime" if _side_effect(step.action) != "none" else "none",
        )
        for step in execution_plan.steps
    )
    permissions = tuple(sorted({step.permission for step in steps}))
    return goal, AgentPlan(goal_id=goal.goal_id, steps=steps, required_permissions=permissions)


def _side_effect(action):
    return "external_write" if action in {"create", "update", "delete", "send", "reply"} else "none"


def _permission(action):
    return "confirm_required" if _side_effect(action) != "none" else "safe"
