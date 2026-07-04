from datetime import datetime

from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class HotelComplaintReportTool:
    """Generate structured hotel complaint reports."""

    metadata = ToolMetadata(
        name="hotel_complaint_report",
        description="Generate manager-style structured complaint reports.",
        domain="hotel",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="hotel",
        aliases=["complaint report", "hotel complaint report", "컴플레인 리포트", "컴플레인 보고서"],
        supported_intents=["complaint report", "manager complaint report", "컴플레인 리포트 작성"],
        examples=[
            "컴플레인 리포트 작성해줘",
            "객실 소음 컴플레인 보고서",
            "hotel complaint report room noise",
        ],
        input_mode="text",
        input_prefixes=["complaint report", "hotel complaint report", "컴플레인 리포트", "컴플레인 보고서"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a structured complaint report."""
        text = str(input_data.get("text", "")).strip()
        occurred_at = str(input_data.get("date_time", "")).strip() or datetime.now().isoformat(timespec="minutes")
        room_number = str(input_data.get("room_number", "")).strip() or infer_room(text)
        guest_claim = str(input_data.get("guest_complaint", "")).strip() or infer_claim(text)
        staff_response = str(input_data.get("staff_response", "")).strip() or "Staff listened, apologized, and checked immediate options."
        cause = str(input_data.get("cause", "")).strip() or infer_cause(text)
        action_taken = str(input_data.get("action_taken", "")).strip() or "Issue logged; room status and available alternatives reviewed."
        compensation = str(input_data.get("compensation", "")).strip() or "Pending manager approval."
        follow_up = str(input_data.get("follow_up", "")).strip() or "Manager follow-up recommended before end of shift."
        summary = f"Room {room_number}: {guest_claim}"
        manager_report = (
            f"[Complaint Report]\nTime: {occurred_at}\nRoom: {room_number}\n"
            f"Claim: {guest_claim}\nResponse: {staff_response}\nCause: {cause}\n"
            f"Action: {action_taken}\nCompensation: {compensation}\nFollow-up: {follow_up}"
        )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "summary": summary,
                "timeline": [
                    {"time": occurred_at, "event": "Complaint received"},
                    {"time": occurred_at, "event": staff_response},
                ],
                "guest_claim": guest_claim,
                "cause": cause,
                "action_taken": action_taken,
                "compensation": compensation,
                "follow_up": follow_up,
                "manager_report": manager_report,
            },
        )


def infer_room(text):
    """Infer a room number from text."""
    for token in text.split():
        if token.isdigit() and len(token) in [3, 4]:
            return token
    return "TBD"


def infer_claim(text):
    """Infer a simple guest claim."""
    if "소음" in text or "noise" in text.lower():
        return "Guest reported room noise disturbance."
    if "청결" in text or "clean" in text.lower():
        return "Guest reported room cleanliness concern."
    if "환불" in text or "refund" in text.lower():
        return "Guest requested refund or compensation."
    return text or "Guest complaint details pending."


def infer_cause(text):
    """Infer a likely cause category."""
    if "소음" in text or "noise" in text.lower():
        return "Possible neighboring room or corridor noise."
    if "청결" in text or "clean" in text.lower():
        return "Room inspection or housekeeping quality issue."
    return "Cause pending investigation."
