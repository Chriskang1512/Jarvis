"""Structural and binding validation for NativeTaskGraph definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from jarvis.native_task_graph.models import (
    BindingSourceType,
    NativeTaskGraph,
)


class ValidationSeverity(str, Enum):
    ERROR = "Error"
    WARNING = "Warning"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: ValidationSeverity
    message: str
    node_id: str = ""
    edge_id: str = ""
    field_path: str = ""
    suggested_fix: str = ""


@dataclass(frozen=True)
class ValidationReport:
    is_valid: bool
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
    graph_id: str
    checked_at: datetime


class NativeTaskGraphValidator:
    def validate(self, graph: NativeTaskGraph) -> ValidationReport:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        def error(code, message, **kwargs):
            errors.append(
                ValidationIssue(code, ValidationSeverity.ERROR, message, **kwargs)
            )

        if not graph.graph_id:
            error("GRAPH_ID_REQUIRED", "GraphId is required.", field_path="graphId")
        if not graph.goal_id:
            error("GOAL_ID_REQUIRED", "GoalId is required.", field_path="goalId")

        node_ids = [node.node_id for node in graph.nodes]
        edge_ids = [edge.edge_id for edge in graph.edges]
        for duplicate in duplicates(node_ids):
            error("DUPLICATE_NODE_ID", f"Duplicate NodeId: {duplicate}", node_id=duplicate)
        for duplicate in duplicates(edge_ids):
            error("DUPLICATE_EDGE_ID", f"Duplicate EdgeId: {duplicate}", edge_id=duplicate)

        known_nodes = set(node_ids)
        for edge in graph.edges:
            if edge.source_node_id not in known_nodes:
                error(
                    "EDGE_SOURCE_NOT_FOUND",
                    f"Source node does not exist: {edge.source_node_id}",
                    edge_id=edge.edge_id,
                    field_path="sourceNodeId",
                )
            if edge.target_node_id not in known_nodes:
                error(
                    "EDGE_TARGET_NOT_FOUND",
                    f"Target node does not exist: {edge.target_node_id}",
                    edge_id=edge.edge_id,
                    field_path="targetNodeId",
                )
            if edge.source_node_id == edge.target_node_id:
                error(
                    "SELF_REFERENCING_EDGE",
                    "An edge cannot reference the same source and target.",
                    edge_id=edge.edge_id,
                )

        cycle = find_cycle(graph)
        if cycle:
            error("CYCLE_DETECTED", f"Cycle detected: {' -> '.join(cycle)}")

        roots = root_node_ids(graph)
        if graph.nodes and not roots:
            error("ROOT_NODE_MISSING", "Graph has no startable root node.")
        if graph.nodes:
            entry = str(graph.metadata.get("entryNodeId", "") or graph.nodes[0].node_id)
            if entry not in known_nodes:
                error("ENTRY_NODE_NOT_FOUND", f"Entry node does not exist: {entry}")
            else:
                reached = reachable_from(graph, entry)
                for node_id in known_nodes - reached:
                    error(
                        "UNREACHABLE_NODE",
                        f"Node is unreachable from entry node {entry}: {node_id}",
                        node_id=node_id,
                        suggested_fix="Connect the node or set an explicit entryNodeId.",
                    )

        if len(graph.nodes) > graph.execution_policy.max_node_count:
            error(
                "MAX_NODE_COUNT_EXCEEDED",
                f"Graph has {len(graph.nodes)} nodes; maximum is "
                f"{graph.execution_policy.max_node_count}.",
            )

        for node in graph.nodes:
            for required_key in node.required_inputs:
                if required_key not in node.inputs:
                    error(
                        "REQUIRED_INPUT_MISSING",
                        f"Required input is missing: {required_key}",
                        node_id=node.node_id,
                        field_path=f"nodes[{node.node_id}].inputs.{required_key}",
                    )
            for input_key, binding in node.inputs.items():
                if (
                    binding.is_required
                    and binding.source_type == BindingSourceType.LITERAL
                    and binding.value is None
                    and binding.default_value is None
                ):
                    error(
                        "REQUIRED_INPUT_MISSING",
                        f"Required literal input has no value: {input_key}",
                        node_id=node.node_id,
                        field_path=f"nodes[{node.node_id}].inputs.{input_key}",
                    )
                if binding.source_type != BindingSourceType.NODE_OUTPUT:
                    continue
                source = graph.node(binding.source_node_id)
                if source is None:
                    error(
                        "BINDING_SOURCE_NODE_NOT_FOUND",
                        f"Binding source node does not exist: {binding.source_node_id}",
                        node_id=node.node_id,
                        field_path=f"inputs.{input_key}.sourceNodeId",
                    )
                    continue
                output = source.outputs.get(binding.source_key)
                if output is None:
                    error(
                        "SOURCE_OUTPUT_NOT_FOUND",
                        f"Source output does not exist: {binding.source_key}",
                        node_id=node.node_id,
                        field_path=f"inputs.{input_key}.sourceKey",
                    )
                elif not types_compatible(output.value_type, binding.expected_type):
                    error(
                        "BINDING_TYPE_MISMATCH",
                        f"{output.value_type} is not compatible with "
                        f"{binding.expected_type}.",
                        node_id=node.node_id,
                        field_path=f"inputs.{input_key}.expectedType",
                    )

        for output in graph.outputs:
            node = graph.node(output.source_node_id)
            if node is None:
                error(
                    "GRAPH_OUTPUT_NODE_NOT_FOUND",
                    f"Graph output node does not exist: {output.source_node_id}",
                    field_path=f"outputs.{output.output_id}.sourceNodeId",
                )
                continue
            definition = node.outputs.get(output.source_output_key)
            if definition is None:
                error(
                    "GRAPH_OUTPUT_KEY_NOT_FOUND",
                    f"Graph output key does not exist: {output.source_output_key}",
                    field_path=f"outputs.{output.output_id}.sourceOutputKey",
                )
            elif not types_compatible(definition.value_type, output.output_type):
                error(
                    "GRAPH_OUTPUT_TYPE_MISMATCH",
                    f"{definition.value_type} is not compatible with "
                    f"{output.output_type}.",
                    field_path=f"outputs.{output.output_id}.outputType",
                )

        return ValidationReport(
            is_valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            graph_id=graph.graph_id,
            checked_at=datetime.now(timezone.utc),
        )


def duplicates(values):
    seen = set()
    repeated = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def adjacency(graph):
    result = {node.node_id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.source_node_id in result:
            result[edge.source_node_id].append(edge.target_node_id)
    return result


def root_node_ids(graph):
    targets = {edge.target_node_id for edge in graph.edges}
    return tuple(node.node_id for node in graph.nodes if node.node_id not in targets)


def reachable_from(graph, entry):
    links = adjacency(graph)
    reached = set()
    stack = [entry]
    while stack:
        current = stack.pop()
        if current in reached:
            continue
        reached.add(current)
        stack.extend(links.get(current, ()))
    return reached


def find_cycle(graph):
    links = adjacency(graph)
    visiting = set()
    visited = set()
    path = []

    def visit(node):
        if node in visiting:
            index = path.index(node)
            return path[index:] + [node]
        if node in visited:
            return []
        visiting.add(node)
        path.append(node)
        for target in links.get(node, ()):
            found = visit(target)
            if found:
                return found
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in links:
        found = visit(node)
        if found:
            return found
    return []


def types_compatible(actual, expected):
    aliases = {
        "str": "string",
        "text": "string",
        "int": "integer",
        "float": "number",
        "double": "number",
        "bool": "boolean",
        "object": "any",
    }
    actual_key = aliases.get(str(actual).strip().lower(), str(actual).strip().lower())
    expected_key = aliases.get(
        str(expected).strip().lower(), str(expected).strip().lower()
    )
    return expected_key == "any" or actual_key == expected_key
