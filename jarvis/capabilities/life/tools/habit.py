from jarvis.capabilities.life.tools.common import default_topic, text_input
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class LifeHabitTool:
    """Create simple habit tracking templates."""

    metadata = ToolMetadata(
        name="life_habit",
        description="Create a habit tracking template for personal routines.",
        domain="life",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="life",
        aliases=["habit", "life habit", "습관", "습관 추적"],
        supported_intents=["habit tracking", "habit template", "습관 만들기", "습관 추적"],
        examples=[
            "운동 습관 추적표 만들어줘",
            "매일 회고 습관",
            "매일 회고 습관 추적표 만들어줘",
            "일본어 공부 습관 체크",
            "habit tracker",
        ],
        input_mode="text",
        input_prefixes=["habit", "life habit", "습관", "습관 추적"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a habit tracking contract."""
        text = text_input(input_data)
        habit = default_topic(text, "daily reflection")

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "habit": habit,
                "tracking_period": "7 days",
                "daily_checklist": [
                    {"day": day, "done": False, "note": ""}
                    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                ],
                "success_rule": "Mark done when the smallest useful version is completed.",
                "notes": [
                    "Alpha habit template only.",
                    "No external habit app is updated.",
                ],
            },
        )
