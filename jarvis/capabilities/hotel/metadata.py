from jarvis.capabilities.metadata import CapabilityMetadata


HOTEL_CAPABILITY_METADATA = CapabilityMetadata(
    id="hotel",
    name="Hotel",
    description="Hospitality operations assistant for front office and rooms division workflows.",
    version="0.1.0-alpha",
    status="alpha",
    owner="Jarvis Team",
    tools=[
        "hotel_schedule_planner",
        "hotel_complaint_report",
        "hotel_complaint_manual",
    ],
    planning_prefix="hotel",
    planning_aliases=["hotel", "front office", "호텔", "프론트"],
    planning_intents={
        "schedule planning": ["schedule", "스케줄", "근무표"],
        "complaint report": ["complaint report", "컴플레인 리포트", "보고서", "리포트"],
        "complaint manual": ["complaint manual", "대응 매뉴얼", "매뉴얼", "대응법"],
    },
    planning_examples=[
        "컴플레인 리포트 작성",
        "대응 매뉴얼 만들어줘",
        "호텔 스케줄 짜줘",
    ],
)
