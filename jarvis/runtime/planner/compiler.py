from dataclasses import dataclass

from jarvis.runtime.planner.journal import PlanValidationJournalEntry
from jarvis.runtime.planner.validation import ValidationStatus


@dataclass(frozen=True)
class PlanCompilationResult:
    """Core decision produced before RuntimeTask execution."""

    status: ValidationStatus
    execution_ready_plan: object | None
    original_validation: object
    optimized_validation: object | None = None
    optimization: object | None = None
    validation_journal: tuple[PlanValidationJournalEntry, ...] = ()

    @property
    def execution_ready(self):
        return self.execution_ready_plan is not None and self.status != ValidationStatus.BLOCKED


class PlanCompiler:
    """Validate, optimize, revalidate, and produce an execution-ready plan."""

    version = "2.0"

    def __init__(self, validator, optimizer):
        self.validator = validator
        self.optimizer = optimizer

    def compile(self, plan):
        original = self.validator.validate(plan)
        journals = [PlanValidationJournalEntry.record(plan, original, self.version)]
        if original.status == ValidationStatus.BLOCKED:
            return PlanCompilationResult(
                status=ValidationStatus.BLOCKED,
                execution_ready_plan=None,
                original_validation=original,
                validation_journal=tuple(journals),
            )

        optimization = self.optimizer.optimize(plan)
        optimized = self.validator.validate(optimization.plan)
        journals.append(
            PlanValidationJournalEntry.record(
                optimization.plan,
                optimized,
                self.version,
            )
        )
        if optimized.status == ValidationStatus.BLOCKED:
            return PlanCompilationResult(
                status=ValidationStatus.BLOCKED,
                execution_ready_plan=None,
                original_validation=original,
                optimized_validation=optimized,
                optimization=optimization,
                validation_journal=tuple(journals),
            )
        return PlanCompilationResult(
            status=optimized.status,
            execution_ready_plan=optimization.plan,
            original_validation=original,
            optimized_validation=optimized,
            optimization=optimization,
            validation_journal=tuple(journals),
        )
