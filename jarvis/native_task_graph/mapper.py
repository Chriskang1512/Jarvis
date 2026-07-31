"""Sprint 1 GoalSpecification to NativeTaskGraph skeleton mapping."""

from __future__ import annotations

from uuid import uuid4

from jarvis.goals import GoalSpecification
from jarvis.native_task_graph.models import NativeTaskGraph


class GoalSpecificationGraphMapper:
    def map(
        self,
        goal: GoalSpecification,
        *,
        conversation_id: str,
        graph_id: str = "",
    ) -> NativeTaskGraph:
        return NativeTaskGraph(
            graph_id=graph_id or f"graph-{uuid4()}",
            goal_id=goal.goal_id,
            conversation_id=conversation_id,
            metadata={
                "objective": goal.objective,
                "originalInput": goal.original_input,
                "goalConfidence": goal.confidence,
                "domain": goal.context.domain,
                "source": "GoalSpecification",
            },
        )
