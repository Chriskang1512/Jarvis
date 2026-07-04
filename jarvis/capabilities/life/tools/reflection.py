from jarvis.capabilities.life.tools.common import default_topic, text_input
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class LifeReflectionTool:
    """Summarize daily or sprint reflections."""

    metadata = ToolMetadata(
        name="life_reflection",
        description="Create a structured reflection with summary, wins, problems, ideas, and next actions.",
        domain="life",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=1,
        capability="life",
        aliases=["reflection", "life reflection", "회고", "오늘 회고", "스프린트 회고"],
        supported_intents=["daily reflection", "sprint retrospective", "회고 정리", "프로젝트 회고"],
        examples=[
            "오늘 회고 정리해줘",
            "자비스 스프린트 회고",
            "오늘 뭐 했는지 정리해줘",
            "문제점과 다음 스프린트 정리",
            "reflection for today",
        ],
        input_mode="text",
        input_prefixes=["reflection", "life reflection", "회고", "오늘 회고", "스프린트 회고"],
        allow_empty_input=True,
        route_confidence=0.82,
    )

    def __init__(self, memory_manager=None):
        """Create reflection tool with optional memory access."""
        self.memory_manager = memory_manager

    def execute(self, input_data):
        """Return a structured reflection, using recent memory when available."""
        text = text_input(input_data)
        topic = default_topic(text, "today")
        memories = recent_memory_dicts(self.memory_manager)
        wins = infer_wins(topic, memories)
        problems = infer_problems(topic, memories)
        ideas = infer_ideas(topic, memories)
        next_actions = infer_next_actions(topic)

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "topic": topic,
                "summary": infer_summary(topic, memories),
                "wins": wins,
                "problems": problems,
                "ideas": ideas,
                "next_actions": next_actions,
                "memory_used": len(memories) > 0,
                "memory": memories[:5],
                "notes": [
                    "Life Alpha reads memory when available but does not own Memory.",
                    "Use this output as a daily or sprint reflection draft.",
                ],
            },
        )


def recent_memory_dicts(memory_manager):
    """Return recent memories as dictionaries when a manager is available."""
    if memory_manager is None:
        return []

    memories = memory_manager.find_by_tag("reflection")

    if len(memories) == 0:
        memories = memory_manager.find_by_tag("jarvis")

    if len(memories) == 0:
        memories = memory_manager.find_recent(limit=5)

    return [memory.to_dict() for memory in memories[:5]]


def infer_summary(topic, memories):
    """Create a planner-readable reflection summary."""
    if len(memories) > 0:
        return f"Reflection for {topic} using {len(memories[:5])} recent memory item(s)."

    return f"Reflection draft for {topic}."


def infer_wins(topic, memories):
    """Create win bullets."""
    if len(memories) > 0:
        return [f"Reviewed memory: {memory['title'] or memory['content'][:60]}" for memory in memories[:3]]

    return [
        f"Captured reflection topic: {topic}",
        "Separated wins, problems, ideas, and next actions.",
    ]


def infer_problems(topic, memories):
    """Create problem bullets."""
    if "problem" in topic.lower() or "문제" in topic:
        return [topic]

    return ["No explicit blocker was provided. Add concrete issues for a sharper review."]


def infer_ideas(topic, memories):
    """Create idea bullets."""
    ideas = ["Turn repeated reflections into Memory-backed routines."]

    if len(memories) > 0:
        ideas.append("Use recent Memory as context for the next planning session.")

    return ideas


def infer_next_actions(topic):
    """Create next action bullets."""
    if "jarvis" in topic.lower() or "자비스" in topic:
        return ["Define the next Jarvis slice", "Keep Core stable", "Add tests before expanding behavior"]

    return ["Pick one next action", "Schedule a review point", "Save durable lessons to Memory"]
