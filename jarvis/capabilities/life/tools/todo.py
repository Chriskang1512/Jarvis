from jarvis.capabilities.life.tools.common import default_topic, split_items, text_input
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class LifeTodoTool:
    """Create practical todo lists and priorities."""

    metadata = ToolMetadata(
        name="life_todo",
        description="Turn personal or project notes into a prioritized todo checklist.",
        domain="life",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="life",
        aliases=["todo", "life todo", "task list", "할 일", "투두"],
        supported_intents=["todo planning", "task breakdown", "할 일 정리", "체크리스트"],
        examples=[
            "오늘 할 일 정리해줘",
            "투두 리스트 만들어줘",
            "다음 스프린트 할 일",
            "make a todo list",
        ],
        input_mode="text",
        input_prefixes=["todo", "life todo", "task list", "할 일", "투두", "체크리스트"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a todo planning contract."""
        text = text_input(input_data)
        topic = default_topic(text, "today")
        raw_items = split_items(text)
        tasks = build_tasks(raw_items, topic)

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "topic": topic,
                "tasks": tasks,
                "priority_order": [task["task"] for task in tasks],
                "notes": [
                    "Alpha planning only: no external task app is updated.",
                    "Use life_reminder for scheduler-ready reminder payloads.",
                ],
            },
        )


def build_tasks(raw_items, topic):
    """Build a compact prioritized task list."""
    if len(raw_items) == 0:
        raw_items = [topic]

    tasks = []
    for index, item in enumerate(raw_items[:5], start=1):
        priority = "high" if index == 1 else "medium"
        tasks.append(
            {
                "task": item,
                "priority": priority,
                "status": "todo",
            }
        )

    return tasks
