"""Builder for tests and deterministic rule-based graph creation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from jarvis.native_task_graph.models import *
from jarvis.native_task_graph.validation import NativeTaskGraphValidator


class NativeTaskGraphBuilder:
    def __init__(
        self,
        graph_id: str,
        goal_id: str,
        conversation_id: str,
        *,
        execution_policy=None,
        metadata=None,
    ):
        self.graph_id = graph_id
        self.goal_id = goal_id
        self.conversation_id = conversation_id
        self.execution_policy = execution_policy or GraphExecutionPolicy()
        self.metadata = dict(metadata or {})
        self._nodes: dict[str, TaskNode] = {}
        self._edges: dict[str, TaskEdge] = {}
        self._outputs: dict[str, GraphOutput] = {}

    def add_node(self, node: TaskNode | None = None, **kwargs):
        node = node or TaskNode(**kwargs)
        if node.node_id in self._nodes:
            raise ValueError(f"Duplicate NodeId: {node.node_id}")
        self._nodes[node.node_id] = node
        return self

    def add_edge(self, edge: TaskEdge | None = None, **kwargs):
        edge = edge or TaskEdge(**kwargs)
        if edge.edge_id in self._edges:
            raise ValueError(f"Duplicate EdgeId: {edge.edge_id}")
        if edge.source_node_id not in self._nodes:
            raise ValueError(f"Unknown source NodeId: {edge.source_node_id}")
        if edge.target_node_id not in self._nodes:
            raise ValueError(f"Unknown target NodeId: {edge.target_node_id}")
        if edge.source_node_id == edge.target_node_id:
            raise ValueError("Self-referencing edges are not allowed.")
        self._edges[edge.edge_id] = edge
        return self

    def bind_literal(
        self, node_id, input_key, value, *, expected_type="Any", is_required=True
    ):
        return self._bind(
            node_id,
            input_key,
            InputBinding(
                BindingSourceType.LITERAL,
                value=value,
                expected_type=expected_type,
                is_required=is_required,
            ),
        )

    def bind_goal_input(
        self, node_id, input_key, source_key, *, expected_type="Any", is_required=True
    ):
        return self._bind_reference(
            node_id,
            input_key,
            BindingSourceType.GOAL_INPUT,
            source_key,
            expected_type,
            is_required,
        )

    def bind_context_slot(
        self, node_id, input_key, source_key, *, expected_type="Any", is_required=True
    ):
        return self._bind_reference(
            node_id,
            input_key,
            BindingSourceType.CONTEXT_SLOT,
            source_key,
            expected_type,
            is_required,
        )

    def bind_artifact_reference(
        self, node_id, input_key, source_key, *, expected_type="Any", is_required=True
    ):
        return self._bind_reference(
            node_id,
            input_key,
            BindingSourceType.ARTIFACT_REFERENCE,
            source_key,
            expected_type,
            is_required,
        )

    def bind_node_output(
        self,
        node_id,
        input_key,
        source_node_id,
        source_output_key,
        *,
        expected_type="Any",
        is_required=True,
    ):
        if source_node_id not in self._nodes:
            raise ValueError(f"Unknown source NodeId: {source_node_id}")
        if source_output_key not in self._nodes[source_node_id].outputs:
            raise ValueError(f"Unknown source output: {source_output_key}")
        return self._bind(
            node_id,
            input_key,
            InputBinding(
                BindingSourceType.NODE_OUTPUT,
                source_node_id=source_node_id,
                source_key=source_output_key,
                expected_type=expected_type,
                is_required=is_required,
            ),
        )

    def add_graph_output(self, output: GraphOutput | None = None, **kwargs):
        output = output or GraphOutput(**kwargs)
        if output.output_id in self._outputs:
            raise ValueError(f"Duplicate GraphOutput id: {output.output_id}")
        self._outputs[output.output_id] = output
        return self

    def build(self):
        return NativeTaskGraph(
            graph_id=self.graph_id,
            goal_id=self.goal_id,
            conversation_id=self.conversation_id,
            nodes=tuple(self._nodes.values()),
            edges=tuple(self._edges.values()),
            outputs=tuple(self._outputs.values()),
            metadata=self.metadata,
            execution_policy=self.execution_policy,
        )

    def build_and_validate(self, validator=None):
        graph = self.build()
        report = (validator or NativeTaskGraphValidator()).validate(graph)
        return graph, report

    def _bind_reference(
        self, node_id, input_key, source_type, source_key, expected_type, is_required
    ):
        return self._bind(
            node_id,
            input_key,
            InputBinding(
                source_type,
                source_key=source_key,
                expected_type=expected_type,
                is_required=is_required,
            ),
        )

    def _bind(self, node_id, input_key, binding):
        if node_id not in self._nodes:
            raise ValueError(f"Unknown NodeId: {node_id}")
        node = self._nodes[node_id]
        inputs = dict(node.inputs)
        if input_key in inputs:
            raise ValueError(f"Input is already bound: {node_id}.{input_key}")
        inputs[input_key] = binding
        self._nodes[node_id] = replace(node, inputs=inputs)
        return self
