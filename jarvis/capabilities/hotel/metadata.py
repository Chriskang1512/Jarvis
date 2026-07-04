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
)
