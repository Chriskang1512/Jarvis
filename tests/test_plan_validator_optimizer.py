import unittest
from dataclasses import replace

from jarvis.abilities import AbilityRegistry, CapabilityOperationMetadata
from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.runtime.planner import (
    AgentPlan,
    AdaptiveExecutionCostModel,
    Availability,
    ExecutionSelectionPolicy,
    HealthReason,
    HealthRecoveryPolicy,
    PlanBinding,
    PlanCompiler,
    PlanStep,
    PlanValidationJournalEntry,
    PlanValidator,
    SmartPlanOptimizer,
    ValidationStatus,
    estimate_plan_cost,
)


class TestPlanValidatorOptimizer(unittest.TestCase):
    def setUp(self):
        self.registry = AbilityRegistry()
        self.registry.register(CalendarAbility(provider=MockCalendarProvider()))

    def register_operation(self, operation, **overrides):
        defaults = {
            "capability": "calendar",
            "operation": operation,
            "input_schema": {"type": "object"},
            "output_schema": "CalendarResult",
            "permission": "safe",
            "side_effect": "none",
            "parallel_safe": True,
            "deduplicatable": True,
        }
        defaults.update(overrides)
        metadata = CapabilityOperationMetadata(**defaults)
        self.registry.register_operation(metadata, replace_existing=True)
        return metadata

    def test_registry_validator_rejects_unknown_operation(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "creat"),),
        )

        result = PlanValidator(self.registry).validate(plan)

        self.assertEqual(result.status, ValidationStatus.BLOCKED)
        self.assertEqual(result.issues[0].code, "UNKNOWN_OPERATION")

    def test_registry_validator_checks_schema_permission_side_effect_and_lifecycle(self):
        self.register_operation(
            "create",
            input_schema={
                "type": "object",
                "required": ["title", "hour"],
                "properties": {"title": {"type": "string"}, "hour": {"type": "integer"}},
            },
            permission="confirm_required",
            side_effect="external_write",
            lifecycle="deprecated",
            parallel_safe=False,
            deduplicatable=False,
        )
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep(
                    "step-1",
                    1,
                    "calendar",
                    "create",
                    input={"title": 3},
                    permission="safe",
                    side_effect="none",
                ),
            ),
        )

        result = PlanValidator(self.registry).validate(plan)
        codes = {issue.code for issue in result.issues}

        self.assertEqual(result.status, ValidationStatus.BLOCKED)
        self.assertIn("INPUT_REQUIRED_FIELD_MISSING", codes)
        self.assertIn("INPUT_FIELD_TYPE_MISMATCH", codes)
        self.assertIn("PERMISSION_MISMATCH", codes)
        self.assertIn("SIDE_EFFECT_MISMATCH", codes)
        self.assertIn("DEPRECATED_CAPABILITY", codes)

    def test_binding_requires_dependency_edge_and_cycle_is_blocked(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep("step-1", 1, "calendar", "list", depends_on=("step-2",)),
                PlanStep("step-2", 2, "calendar", "list", depends_on=("step-1",)),
                PlanStep("step-3", 3, "calendar", "list"),
            ),
            bindings=(PlanBinding("step-3", "events.0", "step-1", "input.event"),),
        )

        codes = {issue.code for issue in PlanValidator(self.registry).validate(plan).issues}

        self.assertIn("DEPENDENCY_CYCLE", codes)
        self.assertIn("DEPENDENCY_MISSING", codes)

    def test_warning_result_allows_deprecated_capability(self):
        self.register_operation("list", lifecycle="deprecated")
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "list"),),
        )

        result = PlanValidator(self.registry).validate(plan)

        self.assertTrue(result.valid)
        self.assertEqual(result.status, ValidationStatus.WARNING)

    def test_smart_optimizer_applies_all_rules_and_journals_reasons(self):
        self.register_operation(
            "create",
            permission="confirm_required",
            side_effect="external_write",
            parallel_safe=False,
            deduplicatable=False,
            required_predecessors=("calendar.list",),
        )
        plan = AgentPlan(
            goal_id="goal-1",
            required_permissions=("confirm_required",),
            steps=(
                PlanStep(
                    "write",
                    4,
                    "calendar",
                    "create",
                    input={"title": "meeting"},
                    depends_on=("read-duplicate",),
                    permission="confirm_required",
                    side_effect="external_write",
                    verification_policy="provider_result",
                    idempotency_policy="operation_id",
                ),
                PlanStep("read-primary", 1, "calendar", "list", input={"date": "today"}),
                PlanStep("read-duplicate", 2, "calendar", "list", input={"date": "today"}),
                PlanStep("read-independent", 3, "calendar", "list", input={"date": "tomorrow"}),
                PlanStep(
                    "dead",
                    5,
                    "calendar",
                    "list",
                    input={"_dead_step": True},
                    required=False,
                ),
            ),
        )

        result = SmartPlanOptimizer(self.registry).optimize(plan)
        optimized = result.plan

        self.assertEqual(
            result.record.rules_applied,
            ("OPT-001", "OPT-004", "OPT-002", "OPT-003"),
        )
        self.assertEqual(
            tuple(step.step_id for step in optimized.steps),
            ("read-primary", "read-independent", "write"),
        )
        write = next(step for step in optimized.steps if step.step_id == "write")
        self.assertEqual(write.depends_on, ("read-primary",))
        parallel = [step.parallel_group for step in optimized.steps[:2]]
        self.assertEqual(parallel, ["PG-1", "PG-1"])
        self.assertTrue(result.record.invariants_verified)
        self.assertEqual(result.record.journal_entries[0].rule_id, "OPT-001")
        self.assertIn("Duplicate", result.record.journal_entries[0].reason)

    def test_validation_journal_replay_returns_identical_result(self):
        self.register_operation("list", lifecycle="deprecated")
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "list"),),
        )
        validator = PlanValidator(self.registry)
        original = validator.validate(plan)
        journal = PlanValidationJournalEntry.record(plan, original, validator_version="2.0")

        replay = journal.replay(validator)

        self.assertTrue(replay.matches)
        self.assertEqual(replay.result.status, ValidationStatus.WARNING)

    def test_validation_journal_redacts_sensitive_plan_values(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep(
                    "step-1",
                    1,
                    "calendar",
                    "list",
                    input={"email": "private@example.com", "body": "secret body"},
                ),
            ),
        )
        validator = PlanValidator(self.registry)

        journal = PlanValidationJournalEntry.record(
            plan,
            validator.validate(plan),
            validator_version="2.0",
        )

        snapshot = str(journal.plan_snapshot)
        self.assertNotIn("private@example.com", snapshot)
        self.assertNotIn("secret body", snapshot)
        self.assertTrue(journal.replay(validator).matches)

    def test_optimizer_never_removes_side_effecting_dead_marked_step(self):
        plan = AgentPlan(
            goal_id="goal-1",
            required_permissions=("confirm_required",),
            steps=(
                PlanStep(
                    "write",
                    1,
                    "calendar",
                    "create",
                    input={"_dead_step": True, "title": "meeting"},
                    required=False,
                    permission="confirm_required",
                    side_effect="external_write",
                    verification_policy="provider_result",
                    idempotency_policy="operation_id",
                ),
            ),
        )

        result = SmartPlanOptimizer(self.registry).optimize(plan)

        self.assertEqual(len(result.plan.steps), 1)
        self.assertNotIn("OPT-004", result.record.rules_applied)

    def test_plan_compiler_blocks_before_optimizer_and_replays_decision(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("step-1", 1, "calendar", "missing"),),
        )
        validator = PlanValidator(self.registry)
        result = PlanCompiler(validator, SmartPlanOptimizer(self.registry)).compile(plan)

        self.assertFalse(result.execution_ready)
        self.assertEqual(result.status, ValidationStatus.BLOCKED)
        self.assertIsNone(result.optimization)
        self.assertEqual(len(result.validation_journal), 1)
        self.assertTrue(result.validation_journal[0].replay(validator).matches)

    def test_plan_compiler_returns_revalidated_execution_ready_plan(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep("read-1", 1, "calendar", "list"),
                PlanStep("read-2", 2, "calendar", "list"),
            ),
        )
        validator = PlanValidator(self.registry)
        result = PlanCompiler(validator, SmartPlanOptimizer(self.registry)).compile(plan)

        self.assertTrue(result.execution_ready)
        self.assertEqual(result.status, ValidationStatus.VALID)
        self.assertEqual(len(result.execution_ready_plan.steps), 1)
        self.assertEqual(len(result.validation_journal), 2)
        self.assertTrue(all(entry.replay(validator).matches for entry in result.validation_journal))

    def test_cost_optimizer_selects_cheaper_equivalent_cache_candidate(self):
        primary = self.registry.get_operation("calendar", "list")
        self.registry.register_operation_candidate(
            replace(
                primary,
                implementation_id="cache:calendar",
                estimated_cost=0.0,
                estimated_latency_ms=2,
                network_required=False,
            )
        )
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        result = SmartPlanOptimizer(self.registry).optimize(plan)

        self.assertEqual(result.plan.steps[0].execution_target, "cache:calendar")
        self.assertIn("OPT-005", result.record.rules_applied)
        entry = next(item for item in result.record.journal_entries if item.rule_id == "OPT-005")
        self.assertLess(
            entry.details["estimated_cost_after"],
            entry.details["estimated_cost_before"],
        )
        self.assertEqual(estimate_plan_cost(result.plan, self.registry).network_operations, 0)

    def test_cost_optimizer_uses_latency_then_local_tie_breakers(self):
        primary = self.registry.get_operation("calendar", "list")
        self.registry.register_operation_candidate(
            replace(
                primary,
                implementation_id="network-fast",
                estimated_cost=0.0,
                estimated_latency_ms=1,
                network_required=True,
            )
        )
        self.registry.register_operation_candidate(
            replace(
                primary,
                implementation_id="local-fast",
                estimated_cost=0.0,
                estimated_latency_ms=1,
                network_required=False,
            )
        )
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        optimized = SmartPlanOptimizer(self.registry).optimize(plan).plan

        self.assertEqual(optimized.steps[0].execution_target, "local-fast")

    def test_cost_optimizer_excludes_cheaper_policy_mismatch(self):
        primary = self.registry.get_operation("calendar", "list")
        self.registry.register_operation_candidate(
            replace(
                primary,
                implementation_id="unsafe-cache",
                estimated_cost=0.0,
                estimated_latency_ms=0,
                permission="confirm_required",
                side_effect="external_write",
            )
        )
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        result = SmartPlanOptimizer(self.registry).optimize(plan)

        self.assertEqual(result.plan.steps[0].execution_target, "")
        self.assertNotIn("OPT-005", result.record.rules_applied)

    def test_validator_blocks_unknown_execution_target(self):
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(
                PlanStep(
                    "read",
                    1,
                    "calendar",
                    "list",
                    execution_target="missing:calendar",
                ),
            ),
        )

        result = PlanValidator(self.registry).validate(plan)

        self.assertEqual(result.status, ValidationStatus.BLOCKED)
        self.assertIn("EXECUTION_TARGET_NOT_FOUND", {issue.code for issue in result.issues})

    def test_adaptive_optimizer_excludes_offline_provider(self):
        primary = self.registry.get_operation("calendar", "list")
        cache = replace(
            primary,
            implementation_id="cache:calendar",
            estimated_cost=2.0,
            reliability_score=0.95,
            network_required=False,
        )
        self.registry.register_operation_candidate(cache)
        metrics = AdaptiveExecutionCostModel()
        metrics.set_availability(primary.id, primary.implementation_id, Availability.OFFLINE)
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        optimized = SmartPlanOptimizer(self.registry, cost_model=metrics).optimize(plan).plan

        self.assertEqual(optimized.steps[0].execution_target, "cache:calendar")

    def test_selection_policy_can_prioritize_reliability_or_cost(self):
        primary = self.registry.get_operation("calendar", "list")
        reliable = replace(
            primary,
            implementation_id="reliable-network",
            estimated_cost=5.0,
            reliability_score=0.99,
        )
        cheap = replace(
            primary,
            implementation_id="cheap-cache",
            estimated_cost=0.0,
            reliability_score=0.95,
            network_required=False,
        )
        self.registry.register_operation(reliable, replace_existing=True)
        self.registry.register_operation_candidate(cheap)
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        reliability_plan = SmartPlanOptimizer(
            self.registry,
            selection_policy=ExecutionSelectionPolicy(reliability_first=True),
        ).optimize(plan).plan
        cost_plan = SmartPlanOptimizer(
            self.registry,
            selection_policy=ExecutionSelectionPolicy(reliability_first=False),
        ).optimize(plan).plan

        self.assertEqual(reliability_plan.steps[0].execution_target, "")
        self.assertEqual(cost_plan.steps[0].execution_target, "cheap-cache")

    def test_runtime_timeout_degrades_provider_and_selects_cache(self):
        primary = self.registry.get_operation("calendar", "list")
        cache = replace(
            primary,
            implementation_id="cache:calendar",
            estimated_cost=0.5,
            reliability_score=0.90,
            network_required=False,
        )
        self.registry.register_operation_candidate(cache)
        metrics = AdaptiveExecutionCostModel()
        metrics.observe(
            primary.id,
            primary.implementation_id,
            success=False,
            latency_ms=2000,
            cost=1.0,
            health_reason=HealthReason.TIMEOUT,
        )
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        result = SmartPlanOptimizer(self.registry, cost_model=metrics).optimize(plan)
        selection = next(
            entry for entry in result.record.journal_entries if entry.rule_id == "OPT-005"
        ).details["selections"]["read"]

        self.assertEqual(result.plan.steps[0].execution_target, "cache:calendar")
        self.assertEqual(selection["availability"], "ONLINE")
        self.assertEqual(selection["health_reason_before"], "TIMEOUT")
        self.assertEqual(selection["health_reason_after"], "NONE")

    def test_dynamic_latency_updates_candidate_ranking(self):
        primary = self.registry.get_operation("calendar", "list")
        cache = replace(
            primary,
            implementation_id="cache:calendar",
            estimated_cost=1.0,
            estimated_latency_ms=500,
            network_required=False,
        )
        self.registry.register_operation_candidate(cache)
        metrics = AdaptiveExecutionCostModel()
        metrics.observe(primary.id, primary.implementation_id, True, latency_ms=100, cost=1.0)
        metrics.observe(cache.id, cache.implementation_id, True, latency_ms=2, cost=1.0)
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        optimized = SmartPlanOptimizer(self.registry, cost_model=metrics).optimize(plan).plan

        self.assertEqual(optimized.steps[0].execution_target, "cache:calendar")

    def test_plan_compiler_uses_online_fallback_for_offline_primary(self):
        primary = self.registry.get_operation("calendar", "list")
        cache = replace(
            primary,
            implementation_id="cache:calendar",
            reliability_score=0.95,
            network_required=False,
        )
        self.registry.register_operation_candidate(cache)
        metrics = AdaptiveExecutionCostModel()
        metrics.set_availability(primary.id, primary.implementation_id, Availability.OFFLINE)
        validator = PlanValidator(self.registry, cost_model=metrics)
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        result = PlanCompiler(
            validator,
            SmartPlanOptimizer(self.registry, cost_model=metrics),
        ).compile(plan)

        self.assertTrue(result.execution_ready)
        self.assertEqual(result.execution_ready_plan.steps[0].execution_target, "cache:calendar")

    def test_plan_compiler_blocks_when_every_candidate_is_offline(self):
        primary = self.registry.get_operation("calendar", "list")
        metrics = AdaptiveExecutionCostModel()
        metrics.set_availability(primary.id, primary.implementation_id, Availability.OFFLINE)
        validator = PlanValidator(self.registry, cost_model=metrics)
        plan = AgentPlan(
            goal_id="goal-1",
            steps=(PlanStep("read", 1, "calendar", "list"),),
        )

        result = PlanCompiler(
            validator,
            SmartPlanOptimizer(self.registry, cost_model=metrics),
        ).compile(plan)

        self.assertFalse(result.execution_ready)
        self.assertEqual(result.status, ValidationStatus.BLOCKED)
        self.assertIn("OPERATION_OFFLINE", {issue.code for issue in result.original_validation.issues})

    def test_health_recovery_policy_maps_stable_reason_codes(self):
        policy = HealthRecoveryPolicy()

        timeout = policy.evaluate(HealthReason.TIMEOUT)
        rate_limit = policy.evaluate(HealthReason.RATE_LIMIT)
        auth = policy.evaluate(HealthReason.AUTH_FAILURE)
        network = policy.evaluate(HealthReason.NETWORK)
        server = policy.evaluate(HealthReason.SERVER_ERROR)
        unknown = policy.evaluate(HealthReason.UNKNOWN)

        self.assertEqual((timeout.action, timeout.retry_after_seconds), ("RETRY_BACKOFF", 30))
        self.assertEqual((rate_limit.action, rate_limit.retry_after_seconds), ("RETRY_AFTER", 300))
        self.assertFalse(auth.retry_allowed)
        self.assertTrue(auth.requires_reauthentication)
        self.assertEqual(auth.action, "REAUTHENTICATE")
        self.assertEqual(network.action, "WAIT_FOR_NETWORK")
        self.assertFalse(network.retry_allowed)
        self.assertEqual((server.action, server.retry_after_seconds), ("RETRY_BACKOFF", 60))
        self.assertEqual(unknown.action, "REQUIRE_VERIFICATION")
        self.assertFalse(unknown.retry_allowed)

    def test_successful_runtime_observation_clears_health_reason(self):
        primary = self.registry.get_operation("calendar", "list")
        metrics = AdaptiveExecutionCostModel()
        metrics.observe(
            primary.id,
            primary.implementation_id,
            False,
            latency_ms=1000,
            health_reason=HealthReason.NETWORK,
        )
        self.assertEqual(
            metrics.profile(primary).health_reason,
            HealthReason.NETWORK,
        )

        metrics.observe(
            primary.id,
            primary.implementation_id,
            True,
            latency_ms=10,
        )

        self.assertEqual(metrics.profile(primary).health_reason, HealthReason.NONE)
        self.assertEqual(metrics.profile(primary).availability, Availability.ONLINE)


if __name__ == "__main__":
    unittest.main()
