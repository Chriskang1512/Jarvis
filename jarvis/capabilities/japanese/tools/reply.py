from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class JapaneseReplyTool:
    """Draft casual Japanese replies."""

    metadata = ToolMetadata(
        name="japanese_reply",
        description="Draft casual Japanese replies for Aya or Yui.",
        domain="japanese",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="japanese",
        aliases=["japanese reply", "jp reply", "reply japanese"],
        supported_intents=["draft japanese reply", "casual japanese reply"],
        examples=[
            "아야에게 답장",
            "reply to aya",
            "japanese reply ユイ 오늘도 수고했어",
            "jp reply yui thanks",
        ],
        input_mode="text",
        input_prefixes=["japanese reply", "jp reply", "reply japanese"],
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a casual Japanese reply draft."""
        text = str(input_data.get("text", "")).strip()
        name = select_preferred_name(text)
        topic = text.replace(name, "").strip() if name != "" else text

        if name == "":
            name = "アヤ"

        if topic == "":
            topic = "오늘도 수고했어"

        reply = {
            "name": name,
            "japanese": f"{name}、今日もおつかれさま。無理しないでね。",
            "korean_meaning": f"{name}, 오늘도 수고했어. 무리하지 마.",
            "tone": "casual and warm",
            "source": topic,
        }
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=reply,
        )


def select_preferred_name(text):
    """Return the preferred Japanese name mentioned in the request."""
    if "ユイ" in text or "yui" in text.lower():
        return "ユイ"

    if "アヤ" in text or "aya" in text.lower():
        return "アヤ"

    return ""
