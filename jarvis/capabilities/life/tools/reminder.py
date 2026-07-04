from jarvis.capabilities.life.tools.common import contains_any, default_topic, text_input
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class LifeReminderTool:
    """Create scheduler-ready reminder payloads without scheduling them."""

    metadata = ToolMetadata(
        name="life_reminder",
        description="Prepare reminder payloads for a future Scheduler without creating real reservations.",
        domain="life",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="life",
        aliases=["reminder", "life reminder", "리마인더", "알림"],
        supported_intents=["reminder draft", "scheduler-ready reminder", "리마인더 생성", "알림 준비"],
        examples=[
            "내일 아침에 회고하라고 알려줘",
            "리마인더 만들어줘",
            "내일 오전에 운동 알림",
            "remind me tomorrow morning",
        ],
        input_mode="text",
        input_prefixes=["reminder", "life reminder", "리마인더", "알림", "알려줘", "remind me"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a reminder payload ready for a future Scheduler."""
        text = text_input(input_data)
        message = default_topic(text, "Check today's priorities.")
        recommended_time = infer_time(text)
        priority = infer_priority(text)

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "message": message,
                "recommended_time": recommended_time,
                "priority": priority,
                "ready_for_scheduler": True,
                "scheduled": False,
                "notes": [
                    "No real reservation was created in Life Alpha.",
                    "A future Scheduler can consume this payload directly.",
                ],
            },
        )


def infer_time(text):
    """Infer a human-readable reminder time."""
    if contains_any(text, ["tomorrow morning", "내일 아침", "내일 오전"]):
        return "tomorrow morning"

    if contains_any(text, ["tomorrow", "내일"]):
        return "tomorrow"

    if contains_any(text, ["tonight", "오늘 밤", "저녁"]):
        return "tonight"

    if contains_any(text, ["morning", "아침", "오전"]):
        return "next morning"

    return "next available planning window"


def infer_priority(text):
    """Infer reminder priority for future Scheduler handoff."""
    if contains_any(text, ["urgent", "high priority", "important"]):
        return "high"

    if contains_any(text, ["low priority"]):
        return "low"

    return "normal"
