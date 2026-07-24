from dataclasses import dataclass
from enum import Enum

from jarvis.runtime.planner.contracts import CONTRACT_VERSION
from jarvis.runtime.planner.versioning import compare_contract_versions, normalize_contract_version


class ValidationStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str = "error"
    step_id: str = ""
    field: str = ""
    message_key: str = ""
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True)
class PlanValidationResult:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self):
        return self.status != ValidationStatus.BLOCKED

    @property
    def status(self):
        if any(issue.severity == "error" for issue in self.issues):
            return ValidationStatus.BLOCKED
        if any(issue.severity == "warning" for issue in self.issues):
            return ValidationStatus.WARNING
        return ValidationStatus.VALID


class PlanValidator:
    """Fail-closed validation for proposed Agent Core plans."""

    def __init__(self, ability_registry, contract_version=CONTRACT_VERSION, cost_model=None):
        self.ability_registry = ability_registry
        self.contract_version = contract_version
        self.cost_model = cost_model

    def validate(self, plan):
        issues = []
        if plan.contract_version != self.contract_version:
            issues.append(ValidationIssue("UNSUPPORTED_CONTRACT_VERSION", field="contract_version"))

        step_ids = [step.step_id for step in plan.steps]
        if len(step_ids) != len(set(step_ids)):
            issues.append(ValidationIssue("DUPLICATE_STEP_ID", field="steps"))

        known_ids = set(step_ids)
        steps_by_id = {step.step_id: step for step in plan.steps}
        for step in plan.steps:
            ability_exists = bool(self.ability_registry.get(step.capability))
            operation = self.ability_registry.get_operation(step.capability, step.operation)
            if not ability_exists:
                issues.append(
                    ValidationIssue(
                        "CAPABILITY_NOT_FOUND",
                        step_id=step.step_id,
                        field="capability",
                        message_key="planner.capability_not_found",
                    )
                )
            elif operation is None:
                issues.append(
                    ValidationIssue(
                        "UNKNOWN_OPERATION",
                        step_id=step.step_id,
                        field="operation",
                        message_key="planner.operation_not_found",
                        actual=step.operation,
                    )
                )
            else:
                issues.extend(
                    validate_operation_contract(
                        step,
                        operation,
                        plan.bindings,
                        plan.contract_version,
                    )
                )
                candidates = self.ability_registry.list_operation_candidates(
                    step.capability,
                    step.operation,
                )
                active_operation = operation
                if step.execution_target:
                    target = next(
                        (
                            candidate
                            for candidate in candidates
                            if candidate.implementation_id == step.execution_target
                        ),
                        None,
                    )
                    if target is None:
                        issues.append(
                            ValidationIssue(
                                "EXECUTION_TARGET_NOT_FOUND",
                                step_id=step.step_id,
                                field="execution_target",
                                actual=step.execution_target,
                            )
                        )
                    elif not execution_target_compatible(operation, target):
                        issues.append(
                            ValidationIssue(
                                "EXECUTION_TARGET_POLICY_MISMATCH",
                                step_id=step.step_id,
                                field="execution_target",
                                expected=operation.implementation_id,
                                actual=target.implementation_id,
                            )
                        )
                    else:
                        active_operation = target
                issues.extend(
                    validate_operation_availability(
                        step,
                        active_operation,
                        operation,
                        candidates,
                        self.cost_model,
                    )
                )
                dependency_operations = {
                    f"{steps_by_id[dependency].capability}.{steps_by_id[dependency].operation}"
                    for dependency in step.depends_on
                    if dependency in steps_by_id
                }
                for required_capability in operation.required_predecessors:
                    if required_capability not in dependency_operations:
                        issues.append(
                            ValidationIssue(
                                "DEPENDENCY_MISSING",
                                step_id=step.step_id,
                                field="depends_on",
                                expected=required_capability,
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
                continue
            target = steps_by_id[binding.target_step_id]
            if binding.source_step_id not in target.depends_on:
                issues.append(
                    ValidationIssue(
                        "DEPENDENCY_MISSING",
                        step_id=binding.target_step_id,
                        field="depends_on",
                        expected=binding.source_step_id,
                    )
                )

        return PlanValidationResult(tuple(issues))


def validate_operation_contract(step, operation, bindings, plan_contract_version):
    issues = []
    if compare_contract_versions(plan_contract_version, operation.contract_version) < 0:
        issues.append(
            ValidationIssue(
                "OPERATION_CONTRACT_VERSION_UNSUPPORTED",
                step_id=step.step_id,
                field="contract_version",
                expected=operation.contract_version,
                actual=plan_contract_version,
            )
        )
    if normalize_contract_version(step.input_schema_version) != normalize_contract_version(
        operation.input_schema_version
    ):
        issues.append(
            ValidationIssue(
                "INPUT_SCHEMA_VERSION_MISMATCH",
                step_id=step.step_id,
                field="input_schema_version",
                expected=operation.input_schema_version,
                actual=step.input_schema_version,
            )
        )
    if normalize_contract_version(step.output_schema_version) != normalize_contract_version(
        operation.output_schema_version
    ):
        issues.append(
            ValidationIssue(
                "OUTPUT_SCHEMA_VERSION_MISMATCH",
                step_id=step.step_id,
                field="output_schema_version",
                expected=operation.output_schema_version,
                actual=step.output_schema_version,
            )
        )
    issues.extend(validate_input_schema(step, operation.input_schema, bindings))
    if not operation.output_schema:
        issues.append(ValidationIssue("OUTPUT_SCHEMA_REQUIRED", step_id=step.step_id, field="output_schema"))
    if step.permission != operation.permission:
        issues.append(
            ValidationIssue(
                "PERMISSION_MISMATCH",
                step_id=step.step_id,
                field="permission",
                expected=operation.permission,
                actual=step.permission,
            )
        )
    if step.side_effect != operation.side_effect:
        issues.append(
            ValidationIssue(
                "SIDE_EFFECT_MISMATCH",
                step_id=step.step_id,
                field="side_effect",
                expected=operation.side_effect,
                actual=step.side_effect,
            )
        )
    if operation.lifecycle == "experimental":
        issues.append(ValidationIssue("EXPERIMENTAL_CAPABILITY", "info", step.step_id, "lifecycle"))
    elif operation.lifecycle == "deprecated":
        issues.append(ValidationIssue("DEPRECATED_CAPABILITY", "warning", step.step_id, "lifecycle"))
    elif operation.lifecycle == "sunset":
        issues.append(ValidationIssue("SUNSET_CAPABILITY", "error", step.step_id, "lifecycle"))
    return issues


def validate_input_schema(step, schema, bindings):
    if not isinstance(step.input, dict):
        return [ValidationIssue("INPUT_SCHEMA_INVALID", step_id=step.step_id, field="input")]
    if not isinstance(schema, dict):
        return [ValidationIssue("INPUT_SCHEMA_REQUIRED", step_id=step.step_id, field="input_schema")]
    schema_type = schema.get("type", "object")
    if schema_type not in {"object", ""} and not str(schema_type).endswith("Query"):
        return ()
    bound_fields = {
        binding.target_path.removeprefix("input.").split(".", 1)[0]
        for binding in bindings
        if binding.target_step_id == step.step_id
    }
    issues = []
    for field_name in schema.get("required", []):
        if field_name not in step.input and field_name not in bound_fields:
            issues.append(
                ValidationIssue(
                    "INPUT_REQUIRED_FIELD_MISSING",
                    step_id=step.step_id,
                    field=f"input.{field_name}",
                )
            )
    for field_name, property_schema in schema.get("properties", {}).items():
        if field_name not in step.input or not isinstance(property_schema, dict):
            continue
        expected_type = property_schema.get("type", "")
        if expected_type and not value_matches_schema_type(step.input[field_name], expected_type):
            issues.append(
                ValidationIssue(
                    "INPUT_FIELD_TYPE_MISMATCH",
                    step_id=step.step_id,
                    field=f"input.{field_name}",
                    expected=expected_type,
                    actual=type(step.input[field_name]).__name__,
                )
            )
    return issues


def value_matches_schema_type(value, expected_type):
    types = {
        "array": (list, tuple),
        "boolean": (bool,),
        "integer": (int,),
        "number": (int, float),
        "object": (dict,),
        "string": (str,),
    }
    return isinstance(value, types.get(expected_type, (object,)))


def execution_target_compatible(primary, target):
    return (
        target.result_equivalence_key == primary.result_equivalence_key
        and target.permission == primary.permission
        and target.side_effect == primary.side_effect
        and target.input_schema == primary.input_schema
        and target.output_schema == primary.output_schema
        and target.lifecycle == primary.lifecycle
    )


def validate_operation_availability(step, active, primary, candidates, cost_model):
    active_availability = operation_availability(active, cost_model)
    active_reason = operation_health_reason(active, cost_model)
    if active_availability == "ONLINE":
        return []
    compatible_alternatives = [
        candidate
        for candidate in candidates
        if candidate.implementation_id != active.implementation_id
        and execution_target_compatible(primary, candidate)
        and operation_availability(candidate, cost_model) == "ONLINE"
    ]
    if not step.execution_target and compatible_alternatives:
        return [
            ValidationIssue(
                "PRIMARY_OPERATION_UNAVAILABLE",
                "warning",
                step.step_id,
                "availability",
                expected="ONLINE alternative",
                actual=f"{active_availability}:{active_reason}",
            )
        ]
    code = "OPERATION_OFFLINE" if active_availability == "OFFLINE" else "OPERATION_DEGRADED"
    severity = "error" if active_availability == "OFFLINE" else "warning"
    return [
        ValidationIssue(
            code,
            severity,
            step.step_id,
            "availability",
            actual=f"{active_availability}:{active_reason}",
        )
    ]


def operation_availability(metadata, cost_model):
    if cost_model is None:
        return metadata.availability
    return cost_model.profile(metadata).availability.value


def operation_health_reason(metadata, cost_model):
    if cost_model is None:
        return metadata.health_reason
    return cost_model.profile(metadata).health_reason.value


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
