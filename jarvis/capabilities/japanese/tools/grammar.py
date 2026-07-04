from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


GRAMMAR_NOTES = {
    "しらない vs わからない": (
        "しらない means 'I do not know the fact/information.' "
        "わからない means 'I do not understand' or 'I cannot figure it out.'"
    ),
    "たのしそう vs たのしみ": (
        "たのしそう describes how something looks: 'looks fun.' "
        "たのしみ is anticipation: 'I am looking forward to it.'"
    ),
    "うれしい vs うれしがる": (
        "うれしい describes the speaker's own happy feeling. "
        "うれしがる describes someone else showing happiness."
    ),
}


class JapaneseGrammarTool:
    """Explain simple Japanese grammar differences."""

    metadata = ToolMetadata(
        name="japanese_grammar",
        description="Explain simple Japanese grammar differences.",
        domain="japanese",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="japanese",
        aliases=["japanese grammar", "jp grammar", "grammar japanese"],
        supported_intents=["explain japanese grammar", "grammar difference"],
        examples=[
            "しらない와 わからない 차이",
            "japanese grammar たのしそう vs たのしみ",
            "grammar Japanese うれしい vs うれしがる",
        ],
        input_mode="text",
        input_prefixes=["japanese grammar", "jp grammar", "grammar japanese"],
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a grammar explanation for known comparison pairs."""
        text = normalize_topic(str(input_data.get("text", "")))
        explanation = GRAMMAR_NOTES.get(text)

        if explanation is None:
            explanation = (
                "I can explain simple Japanese differences. Try: "
                "しらない vs わからない, たのしそう vs たのしみ, or うれしい vs うれしがる."
            )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=explanation,
        )


def normalize_topic(text):
    """Normalize a grammar comparison topic."""
    return " ".join(text.strip().replace("VS", "vs").split())
