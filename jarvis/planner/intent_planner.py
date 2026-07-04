from uuid import uuid4

from jarvis.permissions import PermissionLevel
from jarvis.planner.contracts import ExecutionGraph, PlanEdge, PlanNode, PlannerContract


PLANNER_VERSION = "0.1"
GRAPH_VERSION = "1.0"
DEFAULT_CONFIDENCE = 0.82


class IntentPlanner:
    """Create capability-level intent plans without knowing tools."""

    def __init__(self, capability_registry):
        """Create an intent planner from a CapabilityRegistry."""
        self.capability_registry = capability_registry

    def plan(self, goal):
        """Return a stable planning contract for one user goal."""
        normalized_goal = normalize_text(goal)
        matches = find_capability_intent_matches(
            normalized_goal=normalized_goal,
            original_goal=goal,
            capabilities=self.capability_registry.list_enabled(),
        )
        nodes = create_nodes(matches)
        graph = ExecutionGraph(nodes=nodes, edges=create_edges(nodes))
        requires_planning = len(nodes) > 1

        if not requires_planning:
            graph = ExecutionGraph()

        return PlannerContract(
            plan_id=create_plan_id(),
            planner_version=PLANNER_VERSION,
            graph_version=GRAPH_VERSION,
            goal=goal,
            status="CREATED",
            requires_planning=requires_planning,
            permission_mode=calculate_permission_mode(matches if requires_planning else []),
            execution_mode="sequential",
            graph=graph,
        )


def find_capability_intent_matches(normalized_goal, original_goal, capabilities):
    """Return ordered capability intent matches from capability metadata."""
    matches = []

    for capability in capabilities:
        metadata = capability.metadata
        for intent, terms in metadata.planning_intents.items():
            position = find_first_term_position(normalized_goal, terms)

            if position is None:
                continue

            matches.append(
                {
                    "position": position,
                    "capability": metadata.id,
                    "intent": intent,
                    "input": extract_task_input(original_goal, position),
                    "permission_level": metadata.permission_level,
                    "task_prefix": metadata.planning_prefix or metadata.id,
                }
            )

    return sorted(matches, key=lambda match: match["position"])


def find_first_term_position(normalized_goal, terms):
    """Return the first matching term position, or None."""
    positions = [
        normalized_goal.find(normalize_text(term))
        for term in terms
        if normalize_text(term) != "" and normalize_text(term) in normalized_goal
    ]

    if len(positions) == 0:
        return None

    return min(positions)


def create_nodes(matches):
    """Create graph nodes from ordered capability intent matches."""
    nodes = []

    for index, match in enumerate(matches, start=1):
        nodes.append(
            PlanNode(
                id=f"{normalize_task_prefix(match['task_prefix'])}_{index:03}",
                step=index,
                capability=match["capability"],
                intent=match["intent"],
                input=match["input"],
                status="CREATED",
                required=True,
                confidence=match.get("confidence", DEFAULT_CONFIDENCE),
            )
        )

    return nodes


def create_edges(nodes):
    """Create sequential graph edges for Beta.1."""
    edges = []

    for index in range(len(nodes) - 1):
        edges.append(
            PlanEdge(
                id=f"edge_{index + 1:03}",
                from_node=nodes[index].id,
                to_node=nodes[index + 1].id,
                type="sequential",
            )
        )

    return edges


def calculate_permission_mode(matches):
    """Calculate the highest required permission mode from matched capabilities."""
    levels = [normalize_permission_level(match["permission_level"]) for match in matches]

    if any(level == PermissionLevel.RESTRICTED for level in levels):
        return "RESTRICTED"

    if any(level == PermissionLevel.CONFIRM for level in levels):
        return "CONFIRM"

    return "SAFE"


def normalize_permission_level(level):
    """Return a PermissionLevel from enum or string input."""
    if isinstance(level, PermissionLevel):
        return level

    return PermissionLevel(str(level).lower())


def extract_task_input(original_goal, position):
    """Return a lightweight task input slice for the current planning match."""
    if position <= 0:
        return original_goal.strip()

    return original_goal[position:].strip()


def normalize_text(text):
    """Normalize text for simple metadata matching."""
    return " ".join(str(text).lower().rstrip("?").split())


def create_plan_id():
    """Create a short diagnostic-friendly plan ID."""
    return f"plan_{uuid4().hex[:12]}"


def normalize_task_prefix(prefix):
    """Return a readable task ID prefix from capability metadata."""
    return str(prefix).strip().lower().replace("-", "_")
