"""Diagnostics-only comparison between legacy plans and NativeTaskGraph."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DifferenceSeverity(str, Enum):
    NONE = "None"
    INFO = "Info"
    WARNING = "Warning"
    ERROR = "Error"


@dataclass(frozen=True)
class ShadowDifference:
    field: str
    legacy_value: object
    native_value: object
    severity: DifferenceSeverity


@dataclass(frozen=True)
class ShadowComparisonResult:
    is_equivalent: bool
    differences: tuple[ShadowDifference, ...]
    severity: DifferenceSeverity
    legacy_plan_summary: dict
    native_graph_summary: dict


class ExecutionPlanShadowComparer:
    def compare(self, legacy_plan, native_graph):
        legacy_steps = tuple(getattr(legacy_plan, "steps", ()) or ())
        legacy_caps = tuple(
            canonical_legacy_id(
                getattr(step, "tool_name", getattr(step, "capability", "")),
                getattr(step, "action", getattr(step, "operation", "")),
            )
            for step in legacy_steps
        )
        native_caps = tuple(node.capability_id for node in native_graph.nodes)
        differences = []
        if legacy_caps != native_caps:
            differences.append(
                ShadowDifference(
                    "capability_order",
                    legacy_caps,
                    native_caps,
                    DifferenceSeverity.WARNING,
                )
            )
        legacy_permissions = tuple(
            str(getattr(step, "permission", "safe")) for step in legacy_steps
        )
        native_permissions = tuple(
            node.permission_requirement.value for node in native_graph.nodes
        )
        normalized_legacy_permissions = tuple(
            "ConfirmRequired"
            if value.lower() in {"confirm", "confirm_required"}
            else "Restricted"
            if value.lower() == "restricted"
            else "Safe"
            for value in legacy_permissions
        )
        if normalized_legacy_permissions != native_permissions:
            differences.append(
                ShadowDifference(
                    "permissions",
                    normalized_legacy_permissions,
                    native_permissions,
                    DifferenceSeverity.WARNING,
                )
            )
        severity = (
            max(
                (item.severity for item in differences),
                key=lambda item: list(DifferenceSeverity).index(item),
            )
            if differences
            else DifferenceSeverity.NONE
        )
        return ShadowComparisonResult(
            is_equivalent=not differences,
            differences=tuple(differences),
            severity=severity,
            legacy_plan_summary={
                "capabilities": legacy_caps,
                "stepCount": len(legacy_steps),
            },
            native_graph_summary={
                "capabilities": native_caps,
                "nodeCount": len(native_graph.nodes),
                "outputs": tuple(output.output_type for output in native_graph.outputs),
            },
        )


def canonical_legacy_id(capability, operation):
    from jarvis.capability_planning.registry import CANONICAL_OPERATION_IDS

    raw = f"{capability}.{operation}".strip(".")
    return CANONICAL_OPERATION_IDS.get(raw, raw)
