from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


TRANSLATIONS = {
    "안녕하세요": {
        "hiragana": "こ ん に ち は",
        "japanese": "こんにちは",
        "pronunciation": "곤니치와",
        "meaning": "안녕하세요",
    },
    "고마워": {
        "hiragana": "あ り が と う",
        "japanese": "ありがとう",
        "pronunciation": "아리가토오",
        "meaning": "고마워",
    },
    "잘 자": {
        "hiragana": "お や す み",
        "japanese": "おやすみ",
        "pronunciation": "오야스미",
        "meaning": "잘 자",
    },
    "こんにちは": {
        "hiragana": "こ ん に ち は",
        "japanese": "こんにちは",
        "pronunciation": "곤니치와",
        "meaning": "안녕하세요",
    },
    "ありがとう": {
        "hiragana": "あ り が と う",
        "japanese": "ありがとう",
        "pronunciation": "아리가토오",
        "meaning": "고마워",
    },
}


class JapaneseTranslateTool:
    """Translate small Korean/Japanese learning phrases."""

    metadata = ToolMetadata(
        name="japanese_translate",
        description="Translate simple Korean and Japanese expressions.",
        domain="japanese",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="japanese",
        aliases=["japanese translate", "translate japanese", "jp translate", "translate"],
        supported_intents=["translate to japanese", "translate to korean"],
        examples=[
            "안녕하세요 일본어로",
            "일본어로 번역",
            "translate 안녕하세요",
            "translate japanese 안녕하세요",
            "jp translate ありがとう",
        ],
        input_mode="text",
        input_prefixes=["japanese translate", "translate japanese", "jp translate", "translate"],
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a structured translation for known simple phrases."""
        text = str(input_data.get("text", "")).strip()
        data = TRANSLATIONS.get(text)

        if data is None:
            data = {
                "hiragana": "",
                "japanese": text,
                "pronunciation": "",
                "meaning": "No local translation yet. Try a simple phrase such as 안녕하세요 or ありがとう.",
            }

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=data,
        )
