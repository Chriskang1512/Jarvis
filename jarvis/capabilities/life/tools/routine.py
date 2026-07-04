from jarvis.capabilities.life.tools.common import contains_any, default_topic, text_input
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class LifeRoutineTool:
    """Draft daily or project routines."""

    metadata = ToolMetadata(
        name="life_routine",
        description="Draft morning, evening, study, workout, or project routines.",
        domain="life",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="life",
        aliases=["routine", "life routine", "루틴", "생활 루틴"],
        supported_intents=["routine planning", "daily routine", "루틴 만들기", "생활 계획"],
        examples=[
            "아침 루틴 만들어줘",
            "저녁 회고 루틴",
            "자비스 개발 루틴 짜줘",
            "study routine",
        ],
        input_mode="text",
        input_prefixes=["routine", "life routine", "루틴", "생활 루틴"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a routine draft."""
        text = text_input(input_data)
        routine_type = infer_routine_type(text)
        topic = default_topic(text, routine_type)

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "routine_type": routine_type,
                "topic": topic,
                "steps": build_steps(routine_type),
                "notes": [
                    "Alpha routine draft only.",
                    "Save repeated routines to Memory when they become stable.",
                ],
            },
        )


def infer_routine_type(text):
    """Infer routine type from text."""
    if contains_any(text, ["morning", "아침", "오전"]):
        return "morning"
    if contains_any(text, ["evening", "night", "저녁", "밤"]):
        return "evening"
    if contains_any(text, ["study", "공부", "일본어"]):
        return "study"
    if contains_any(text, ["workout", "운동"]):
        return "workout"
    if contains_any(text, ["project", "sprint", "자비스", "프로젝트"]):
        return "project"
    return "daily"


def build_steps(routine_type):
    """Return default steps for the routine type."""
    templates = {
        "morning": ["Check schedule", "Pick top 3 tasks", "Start first focused block"],
        "evening": ["Review today", "Capture problems", "Choose tomorrow's first task"],
        "study": ["Warm-up review", "Practice one focused topic", "Save new expressions"],
        "workout": ["Warm up", "Main set", "Cooldown and record"],
        "project": ["Review current sprint", "Pick next implementation slice", "Run tests and note risks"],
        "daily": ["Plan", "Execute", "Reflect"],
    }
    return templates.get(routine_type, templates["daily"])
