from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


DEFAULT_STAFF = ["민경", "도현", "예주", "서윤"]
DEFAULT_CODES = {
    "D": "09:00-18:00",
    "E": "13:00-22:00",
    "N": "22:00-07:00",
    "OFF": "day off",
}
DEFAULT_CONSTRAINTS = [
    "weekend minimum 2 staff",
    "no D after N",
    "max consecutive N is 2",
    "monthly OFF 8 per staff",
]


class HotelSchedulePlannerTool:
    """Draft hotel staff schedules and surface unresolved constraints."""

    metadata = ToolMetadata(
        name="hotel_schedule_planner",
        description="Draft front office schedules with editable rules, requests, and conflict notes.",
        domain="hotel",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="hotel",
        aliases=["hotel schedule", "front schedule", "schedule planner", "근무표", "호텔 스케줄"],
        supported_intents=["hotel schedule planning", "front office schedule", "직원 스케줄", "근무표 작성"],
        examples=[
            "호텔 스케줄 짜줘",
            "프론트 근무표 만들어줘",
            "직원 휴무 반영해서 스케줄 만들어줘",
            "schedule planner front office",
        ],
        input_mode="text",
        input_prefixes=["hotel schedule", "front schedule", "schedule planner", "호텔 스케줄", "프론트 근무표", "근무표"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a draft schedule with conflicts and unresolved constraints."""
        text = str(input_data.get("text", "")).strip()
        staff = normalize_list(input_data.get("staff"), DEFAULT_STAFF)
        schedule_codes = input_data.get("schedule_codes")
        if not isinstance(schedule_codes, dict):
            schedule_codes = DEFAULT_CODES.copy()

        requests = normalize_list(input_data.get("requests"), parse_requests(text))
        constraints = normalize_list(input_data.get("constraints"), DEFAULT_CONSTRAINTS)
        draft_schedule = build_draft_schedule(staff)
        conflicts = detect_conflicts(draft_schedule, requests, constraints)
        notes = [
            "Alpha draft only: review manually before publishing.",
            "Schedule code labels are editable through schedule_codes.",
            "Add custom constraints as text; unresolved constraints are returned for manager review.",
        ]

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "staff": staff,
                "schedule_codes": schedule_codes,
                "constraints": constraints,
                "requests": requests,
                "draft_schedule": draft_schedule,
                "conflicts": conflicts,
                "notes": notes,
            },
        )


def normalize_list(value, default):
    """Return list input or default list."""
    if isinstance(value, list):
        return value

    return list(default)


def parse_requests(text):
    """Extract simple request notes from text."""
    requests = []
    if "휴무" in text or "off" in text.lower():
        requests.append("requested off-days included when specified")
    if "야간 제외" in text:
        requests.append("night shift exclusion requested")
    return requests


def build_draft_schedule(staff):
    """Build a small deterministic weekly schedule draft."""
    days = ["6/10", "6/11", "6/12", "6/13", "6/14", "6/15", "6/16"]
    pattern = ["D", "E", "N", "OFF"]
    draft = {}
    for index, day in enumerate(days):
        draft[day] = {}
        for staff_index, name in enumerate(staff):
            draft[day][name] = pattern[(index + staff_index) % len(pattern)]
    return draft


def detect_conflicts(draft_schedule, requests, constraints):
    """Return alpha-level conflicts and unresolved constraints."""
    conflicts = []
    if len(requests) > 0:
        conflicts.append("Staff requests detected; verify exact dates before publishing.")

    for day, assignments in draft_schedule.items():
        working_count = len([code for code in assignments.values() if code != "OFF"])
        if day in ["6/15", "6/16"] and working_count < 2:
            conflicts.append(f"{day}: weekend minimum 2 staff condition may be unmet.")

    conflicts.append("Night-to-D rule requires manager review in alpha planner.")
    for constraint in constraints:
        if "A와 B" in constraint or "same team" in constraint.lower():
            conflicts.append(f"Unresolved custom constraint: {constraint}")
    return conflicts
