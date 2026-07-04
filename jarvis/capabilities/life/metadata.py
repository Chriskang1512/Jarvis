from jarvis.capabilities.metadata import CapabilityMetadata


LIFE_CAPABILITY_METADATA = CapabilityMetadata(
    id="life",
    name="Life",
    description="Personal life assistant for memory-adjacent routines, todos, reminders, habits, and reflections.",
    version="0.1.0-alpha",
    status="alpha",
    owner="Jarvis Team",
    tools=[
        "life_todo",
        "life_reminder",
        "life_routine",
        "life_habit",
        "life_reflection",
    ],
    planning_prefix="life",
    planning_aliases=["life", "daily", "생활", "오늘"],
    planning_intents={
        "todo planning": ["todo", "할 일", "투두", "체크리스트"],
        "reminder draft": ["reminder", "리마인더", "알림"],
        "routine planning": ["routine", "루틴"],
        "habit tracking": ["habit", "습관"],
        "reflection": ["reflection", "회고"],
    },
    planning_examples=[
        "오늘 할 일 정리",
        "회고 정리",
        "루틴 만들기",
    ],
)
