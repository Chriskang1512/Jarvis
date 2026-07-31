"""Registry, schema, permission and success-criterion planning validation."""

from __future__ import annotations

from datetime import datetime, timezone

from jarvis.capability_planning.models import SuccessCriterionMapping
from jarvis.native_task_graph import (
    BindingSourceType,
    NativeTaskGraphValidator,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)
from jarvis.native_task_graph.validation import types_compatible


class CapabilityPlanValidator:
    def __init__(self, graph_validator=None):
        self.graph_validator = graph_validator or NativeTaskGraphValidator()

    def validate(self, graph, snapshot, *, goal=None, mappings=(), max_nodes=None):
        base = self.graph_validator.validate(graph)
        errors = list(base.errors)
        warnings = list(base.warnings)

        def error(code, message, node_id="", field_path="", suggested_fix=""):
            errors.append(
                ValidationIssue(
                    code,
                    ValidationSeverity.ERROR,
                    message,
                    node_id=node_id,
                    field_path=field_path,
                    suggested_fix=suggested_fix,
                )
            )

        if max_nodes is not None and len(graph.nodes) > max_nodes:
            error(
                "PLANNING_MAX_NODE_COUNT_EXCEEDED",
                f"Planner produced {len(graph.nodes)} nodes; policy allows {max_nodes}.",
            )

        for node in graph.nodes:
            if node.node_type.value in {"Result", "NoOp", "UserConfirmation"}:
                continue
            descriptor = snapshot.get(node.capability_id)
            if descriptor is None:
                error(
                    "UNREGISTERED_CAPABILITY",
                    f"Capability is not in snapshot: {node.capability_id}",
                    node_id=node.node_id,
                    suggested_fix="Select a CapabilityId from the supplied snapshot.",
                )
                continue
            if has_provider_name(node.capability_id):
                error(
                    "PROVIDER_SPECIFIC_CAPABILITY",
                    "Planner cannot select a provider-specific CapabilityId.",
                    node_id=node.node_id,
                )
            if node.operation != descriptor.operation:
                error(
                    "CAPABILITY_OPERATION_MISMATCH",
                    f"Expected operation {descriptor.operation}, got {node.operation}.",
                    node_id=node.node_id,
                )
            if permission_rank(node.permission_requirement) < permission_rank(
                descriptor.permission_requirement
            ):
                error(
                    "PERMISSION_DOWNGRADE",
                    f"{node.capability_id} requires "
                    f"{descriptor.permission_requirement.value}.",
                    node_id=node.node_id,
                )
            for definition in descriptor.input_schema:
                binding = node.inputs.get(definition.name)
                if definition.is_required and binding is None:
                    error(
                        "CAPABILITY_REQUIRED_INPUT_MISSING",
                        f"Required capability input is missing: {definition.name}",
                        node_id=node.node_id,
                        field_path=f"inputs.{definition.name}",
                    )
                    continue
                if binding is None:
                    continue
                if not types_compatible(binding.expected_type, definition.value_type):
                    error(
                        "CAPABILITY_INPUT_TYPE_MISMATCH",
                        f"Input {definition.name} expects {definition.value_type}, "
                        f"binding declares {binding.expected_type}.",
                        node_id=node.node_id,
                        field_path=f"inputs.{definition.name}.expectedType",
                    )
                if (
                    definition.allowed_sources
                    and binding.source_type not in definition.allowed_sources
                ):
                    error(
                        "CAPABILITY_INPUT_SOURCE_NOT_ALLOWED",
                        f"{binding.source_type.value} is not allowed for "
                        f"{definition.name}.",
                        node_id=node.node_id,
                    )
            for definition in descriptor.output_schema:
                output = node.outputs.get(definition.name)
                if definition.is_required and output is None:
                    error(
                        "CAPABILITY_OUTPUT_MISSING",
                        f"Required capability output is missing: {definition.name}",
                        node_id=node.node_id,
                    )
                elif output and not types_compatible(
                    output.value_type, definition.value_type
                ):
                    error(
                        "CAPABILITY_OUTPUT_TYPE_MISMATCH",
                        f"Output {definition.name} must be {definition.value_type}.",
                        node_id=node.node_id,
                    )

        if goal is not None:
            mapped = {item.criterion_id for item in mappings}
            for criterion in goal.success_criteria:
                criterion_id = criterion.criterion_id
                if criterion.required and criterion_id not in mapped:
                    error(
                        "SUCCESS_CRITERION_UNMAPPED",
                        f"Required success criterion is not mapped: {criterion_id}",
                    )

        return ValidationReport(
            is_valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            graph_id=graph.graph_id,
            checked_at=datetime.now(timezone.utc),
        )


def permission_rank(value):
    return {"Safe": 0, "ConfirmRequired": 1, "Restricted": 2}.get(
        getattr(value, "value", str(value)), 0
    )


def has_provider_name(capability_id):
    lowered = str(capability_id).lower()
    return lowered.startswith(
        ("google_", "google.", "gmail.", "outlook.", "openweather.")
    )
