import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.runtime.planner import (
    AgentPlan,
    ExecutionPlan,
    ExecutionStep,
    NoOpPlanOptimizer,
    PlanBinding,
    PlanStep,
    PlanValidator,
    adapt_execution_plan,
)


class TestAgentCorePlannerContract(unittest.TestCase):
    def setUp(self):
        self.registry = AbilityRegistry()
        self.registry.register(CalendarAbility(provider=MockCalendarProvider()))

    def test_legacy_plan_adapts_to_versioned_goal_and_plan(self):
        legacy = ExecutionPlan(
            raw_text="create calendar event",
            steps=(
                ExecutionStep(index=1, tool_name="calendar", action="list"),
                ExecutionStep(index=2, tool_name="calendar", action="create", depends_on=(1,)),
            ),
        )

        goal, plan = adapt_execution_plan(legacy, conversation_id="conversation-1")

        self.assertEqual(goal.conversation_id, "conversation-1")
        self.assertEqual(plan.steps[1].depends_on, ("STEP-1",))
        self.assertEqual(plan.steps[1].side_effect, "external_write")
        self.assertEqual(plan.steps[1].permission, "confirm_required")

    def test_validator_accepts_registered_safe_capability(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "list"),),
        )

        result = PlanValidator(self.registry).validate(plan)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, ())

    def test_validator_rejects_unknown_capability_and_dependency_cycle(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep("step-1", 1, "missing", "run", depends_on=("step-2",)),
                PlanStep("step-2", 2, "calendar", "list", depends_on=("step-1",)),
            ),
        )

        codes = {issue.code for issue in PlanValidator(self.registry).validate(plan).issues}

        self.assertIn("CAPABILITY_NOT_FOUND", codes)
        self.assertIn("DEPENDENCY_CYCLE", codes)

    def test_external_write_requires_permission_verification_and_idempotency(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep(
                    "step-1",
                    1,
                    "calendar",
                    "create",
                    side_effect="external_write",
                ),
            ),
        )

        codes = {issue.code for issue in PlanValidator(self.registry).validate(plan).issues}

        self.assertIn("SIDE_EFFECT_PERMISSION_REQUIRED", codes)
        self.assertIn("VERIFICATION_POLICY_REQUIRED", codes)
        self.assertIn("IDEMPOTENCY_POLICY_REQUIRED", codes)

    def test_noop_optimizer_versions_plan_without_semantic_change(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "list"),),
        )

        result = NoOpPlanOptimizer().optimize(plan)

        self.assertEqual(result.plan.plan_version, 2)
        self.assertEqual(result.plan.optimized_from_version, 1)
        self.assertEqual(
            result.record.semantic_fingerprint_before,
            result.record.semantic_fingerprint_after,
        )

    def test_semantic_fingerprint_changes_when_binding_changes(self):
        step_one = PlanStep("step-1", 1, "calendar", "list")
        step_two = PlanStep("step-2", 2, "calendar", "create", depends_on=("step-1",))
        first = AgentPlan(
            goal_id="goal-1",
            steps=(step_one, step_two),
            bindings=(PlanBinding("step-1", "event.start", "step-2", "start"),),
        )
        changed = AgentPlan(
            goal_id="goal-1",
            steps=(step_one, step_two),
            bindings=(PlanBinding("step-1", "event.end", "step-2", "start"),),
        )

        self.assertNotEqual(first.semantic_fingerprint(), changed.semantic_fingerprint())


if __name__ == "__main__":
    unittest.main()
