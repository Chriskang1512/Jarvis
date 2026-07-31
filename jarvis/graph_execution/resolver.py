"""Resolve structured NativeTaskGraph input bindings."""
from __future__ import annotations

from jarvis.native_task_graph import BindingSourceType


class InputBindingResolver:
    def resolve(
        self,
        node,
        output_store,
        *,
        goal_inputs=None,
        context_slots=None,
        entities=None,
        previous_results=None,
        user_preferences=None,
        artifacts=None,
        system_values=None,
    ):
        sources = {
            BindingSourceType.GOAL_INPUT: goal_inputs or {},
            BindingSourceType.CONTEXT_SLOT: context_slots or {},
            BindingSourceType.ENTITY_REFERENCE: entities or {},
            BindingSourceType.PREVIOUS_RESULT: previous_results or {},
            BindingSourceType.USER_PREFERENCE: user_preferences or {},
            BindingSourceType.ARTIFACT_REFERENCE: artifacts or {},
            BindingSourceType.SYSTEM_VALUE: system_values or {},
        }
        resolved = {}
        for name, binding in node.inputs.items():
            if binding.source_type == BindingSourceType.LITERAL:
                value = binding.value
            elif binding.source_type == BindingSourceType.NODE_OUTPUT:
                value = output_store.get(
                    binding.source_node_id, binding.source_key
                ).value
            else:
                value = sources[binding.source_type].get(binding.source_key)
            if value is None:
                value = binding.default_value
            if value is None and binding.is_required:
                raise ValueError(f"Required input could not be resolved: {node.node_id}.{name}")
            resolved[name] = apply_transformation(value, binding.transformation)
        for name in node.required_inputs:
            if resolved.get(name) is None:
                raise ValueError(f"Required input is missing: {node.node_id}.{name}")
        return resolved


def apply_transformation(value, transformation):
    transformation = str(transformation or "").strip().lower()
    if not transformation:
        return value
    if transformation == "string":
        return str(value)
    if transformation == "first":
        return value[0] if value else None
    raise ValueError(f"Unsupported binding transformation: {transformation}")
