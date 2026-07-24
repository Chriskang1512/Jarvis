from dataclasses import dataclass

from jarvis.runtime.planner.contracts import CONTRACT_VERSION


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str = "error"
    step_id: str = ""
    field: str = ""
    message_key: str = ""


@dataclass(frozen=True)
class PlanValidationResult:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self):
        return not any(issue.severity == "error" for issue in self.issues)


class PlanValidator:
    """Fail-closed validation for proposed Agent Core plans."""

    def __init__(self, ability_registry, contract_version=CONTRACT_VERSION):
        self.ability_registry = ability_registry
        self.contract_version = contract_version

    def validate(self, plan):
        issues = []
        if plan.contract_version != self.contract_version:
            issues.append(ValidationIssue("UNSUPPORTED_CONTRACT_VERSION", field="contract_version"))

        step_ids = [step.step_id for step in plan.steps]
        if len(step_ids) != len(set(step_ids)):
            issues.append(ValidationIssue("DUPLICATE_STEP_ID", field="steps"))

        known_ids = set(step_ids)
        for step in plan.steps:
            capability_id = f"{step.capability}.{step.operation}" if step.operation else step.capability
            capability_exists = bool(self.ability_registry.find_by_capability(capability_id))
            ability_exists = bool(self.ability_registry.get(step.capability))
            if not capability_exists and not ability_exists:
                issues.append(
                    ValidationIssue(
                        "CAPABILITY_NOT_FOUND",
                        step_id=step.step_id,
                        field="capability",
                        message_key="planner.capability_not_found",
                    )
                )
            for dependency in step.depends_on:
                if dependency not in known_ids:
                    issues.append(ValidationIssue("DEPENDENCY_NOT_FOUND", step_id=step.step_id, field="depends_on"))
            if step.side_effect != "none" and step.permission == "safe":
                issues.append(ValidationIssue("SIDE_EFFECT_PERMISSION_REQUIRED", step_id=step.step_id, field="permission"))
            if step.side_effect == "external_write":
                if step.verification_policy == "none":
                    issues.append(ValidationIssue("VERIFICATION_POLICY_REQUIRED", step_id=step.step_id))
                if step.idempotency_policy == "none":
                    issues.append(ValidationIssue("IDEMPOTENCY_POLICY_REQUIRED", step_id=step.step_id))

        if _has_cycle(plan.steps):
            issues.append(ValidationIssue("DEPENDENCY_CYCLE", field="depends_on"))

        for binding in plan.bindings:
            if binding.source_step_id not in known_ids or binding.target_step_id not in known_ids:
                issues.append(ValidationIssue("BINDING_STEP_NOT_FOUND", field="bindings"))

        return PlanValidationResult(tuple(issues))


def _has_cycle(steps):
    graph = {step.step_id: tuple(step.depends_on) for step in steps}
    visiting = set()
    visited = set()

    def visit(step_id):
        if step_id in visiting:
            return True
        if step_id in visited:
            return False
        visiting.add(step_id)
        for dependency in graph.get(step_id, ()):
            if dependency in graph and visit(dependency):
                return True
        visiting.remove(step_id)
        visited.add(step_id)
        return False

    return any(visit(step_id) for step_id in graph)
