from dataclasses import dataclass

from jarvis.runtime.planner.contracts import agent_plan_from_dict, agent_plan_to_dict


@dataclass(frozen=True)
class PlanValidationJournalEntry:
    """Serializable Validator decision used for deterministic replay."""

    plan_snapshot: dict
    result_snapshot: dict
    validator_version: str

    @classmethod
    def record(cls, plan, result, validator_version):
        return cls(
            plan_snapshot=agent_plan_to_dict(plan, redact_inputs=True),
            result_snapshot=validation_result_to_dict(result),
            validator_version=validator_version,
        )

    def replay(self, validator):
        replayed = validator.validate(agent_plan_from_dict(self.plan_snapshot))
        return PlanValidationReplayResult(
            result=replayed,
            matches=validation_result_to_dict(replayed) == self.result_snapshot,
        )


@dataclass(frozen=True)
class PlanValidationReplayResult:
    result: object
    matches: bool


def validation_result_to_dict(result):
    return {
        "status": result.status.value,
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "step_id": issue.step_id,
                "field": issue.field,
                "message_key": issue.message_key,
                "expected": issue.expected,
                "actual": issue.actual,
            }
            for issue in result.issues
        ],
    }
