from dataclasses import dataclass, field


@dataclass
class PlanNode:
    """One capability-level planning task."""

    id: str
    step: int
    capability: str
    intent: str
    input: str
    status: str = "CREATED"
    required: bool = True
    confidence: float = 0.0

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "id": self.id,
            "step": self.step,
            "capability": self.capability,
            "intent": self.intent,
            "input": self.input,
            "status": self.status,
            "required": self.required,
            "confidence": self.confidence,
        }


@dataclass
class PlanEdge:
    """One graph edge between planning tasks."""

    id: str
    from_node: str
    to_node: str
    type: str = "sequential"

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "id": self.id,
            "from": self.from_node,
            "to": self.to_node,
            "type": self.type,
        }


@dataclass
class ExecutionGraph:
    """Graph-shaped planning structure, executed sequentially in Beta.1."""

    nodes: list[PlanNode] = field(default_factory=list)
    edges: list[PlanEdge] = field(default_factory=list)
    # Reserved for future execution metadata such as cost, tokens, and timing.
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": dict(self.metadata),
        }


@dataclass
class PlannerContract:
    """Stable planner output contract for capability orchestration."""

    plan_id: str
    planner_version: str
    graph_version: str
    goal: str
    status: str
    requires_planning: bool
    permission_mode: str
    execution_mode: str
    graph: ExecutionGraph

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "plan_id": self.plan_id,
            "planner_version": self.planner_version,
            "graph_version": self.graph_version,
            "goal": self.goal,
            "status": self.status,
            "requires_planning": self.requires_planning,
            "permission_mode": self.permission_mode,
            "execution_mode": self.execution_mode,
            "graph": self.graph.to_dict(),
        }
