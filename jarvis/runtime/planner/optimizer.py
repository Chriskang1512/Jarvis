from dataclasses import dataclass, replace


@dataclass(frozen=True)
class OptimizationRecord:
    optimizer_version: str
    input_plan_version: int
    output_plan_version: int
    rules_applied: tuple[str, ...]
    semantic_fingerprint_before: str
    semantic_fingerprint_after: str


@dataclass(frozen=True)
class OptimizationResult:
    plan: object
    record: OptimizationRecord


class NoOpPlanOptimizer:
    """Auditable optimizer boundary that preserves plan semantics."""

    version = "1.0-noop"

    def optimize(self, plan):
        before = plan.semantic_fingerprint()
        optimized = replace(
            plan,
            status="optimized",
            plan_version=plan.plan_version + 1,
            optimized_from_version=plan.plan_version,
        )
        after = optimized.semantic_fingerprint()
        if before != after:
            raise ValueError("OPTIMIZER_SEMANTIC_CHANGE")
        return OptimizationResult(
            plan=optimized,
            record=OptimizationRecord(
                optimizer_version=self.version,
                input_plan_version=plan.plan_version,
                output_plan_version=optimized.plan_version,
                rules_applied=(),
                semantic_fingerprint_before=before,
                semantic_fingerprint_after=after,
            ),
        )
