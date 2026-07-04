from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


SCENARIOS = {
    "noise": {
        "scenario": "소음 컴플레인",
        "first_response": "불편을 드려 죄송합니다. 즉시 소음 원인을 확인하고 조치하겠습니다.",
        "do": ["경청하고 사과한다", "객실/층 상황을 확인한다", "가능하면 객실 이동 또는 귀마개 등 대안을 제시한다"],
        "dont": ["고객 탓으로 돌리지 않는다", "확인 전 보상을 약속하지 않는다"],
        "escalation": ["반복 소음", "수면 방해 지속", "고성/폭력 가능성"],
        "sample_script": "고객님, 불편을 드려 죄송합니다. 지금 바로 현장 확인 후 가능한 조치를 안내드리겠습니다.",
        "manager_notes": "반복 발생 시 객실 이동, late checkout, 보상 여부 검토.",
    },
    "refund": {
        "scenario": "환불 요구",
        "first_response": "불편 사항을 정확히 확인한 뒤 규정과 가능한 보상안을 안내드리겠습니다.",
        "do": ["사실관계를 기록한다", "예약 조건을 확인한다", "매니저 승인 기준을 안내한다"],
        "dont": ["즉석에서 전액 환불을 확정하지 않는다", "감정적으로 반응하지 않는다"],
        "escalation": ["전액 환불 요구", "법적 조치 언급", "고성/욕설"],
        "sample_script": "환불 가능 여부는 예약 조건과 상황 확인이 필요합니다. 제가 먼저 내용을 정리해 매니저에게 보고드리겠습니다.",
        "manager_notes": "증빙, 객실 상태, 대응 시간, 대체 제공 여부 확인.",
    },
}


class HotelComplaintManualTool:
    """Generate complaint response SOP guidance."""

    metadata = ToolMetadata(
        name="hotel_complaint_manual",
        description="Generate SOP-style complaint response guidance.",
        domain="hotel",
        version="0.1.0",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        deprecated=False,
        priority=0,
        capability="hotel",
        aliases=["complaint manual", "hotel sop", "complaint sop", "컴플레인 대응 매뉴얼", "대응 매뉴얼"],
        supported_intents=["complaint response manual", "hotel complaint sop", "고객 대응 매뉴얼"],
        examples=[
            "컴플레인 대응 매뉴얼",
            "환불 요구 고객 대응법",
            "고객이 욕할 때 대응 매뉴얼",
            "소음 컴플레인 대응 매뉴얼",
        ],
        input_mode="text",
        input_prefixes=["complaint manual", "hotel sop", "complaint sop", "컴플레인 대응 매뉴얼", "대응 매뉴얼"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return SOP guidance for a complaint scenario."""
        text = str(input_data.get("text", "")).strip()
        scenario_key = detect_scenario(text)
        data = SCENARIOS.get(scenario_key, generic_manual(text))

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "tool": self.metadata.name,
                "scenario": data["scenario"],
                "first_response": data["first_response"],
                "do": data["do"],
                "dont": data["dont"],
                "escalation 기준": data["escalation"],
                "sample_script": data["sample_script"],
                "manager_notes": data["manager_notes"],
            },
        )


def detect_scenario(text):
    """Detect complaint scenario from text."""
    lowered = text.lower()
    if "환불" in text or "refund" in lowered:
        return "refund"
    if "소음" in text or "noise" in lowered:
        return "noise"
    return "generic"


def generic_manual(text):
    """Return generic complaint SOP guidance."""
    scenario = text or "일반 컴플레인"
    return {
        "scenario": scenario,
        "first_response": "불편을 드려 죄송합니다. 상황을 확인하고 가능한 조치를 안내드리겠습니다.",
        "do": ["경청", "사과", "사실 확인", "기록", "매니저 공유"],
        "dont": ["논쟁하지 않기", "무단 보상 약속 금지", "고객 감정 무시 금지"],
        "escalation": ["안전 이슈", "욕설/고성", "환불/보상 요구", "반복 컴플레인"],
        "sample_script": "말씀 주신 내용을 제가 정확히 확인하고, 가능한 조치와 소요 시간을 바로 안내드리겠습니다.",
        "manager_notes": "시간, 객실, 고객 요청, 직원 대응, 후속 조치 필요 여부를 기록.",
    }
