from jarvis.capabilities.creator.tools.common import asset_header, default_idea, detect_language
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class CreatorLyricsTool:
    """Generate reusable song lyrics."""

    metadata = ToolMetadata(
        name="creator_lyrics",
        description="Generate song lyrics from a creative idea.",
        domain="creator",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="creator",
        aliases=["creator lyrics", "lyrics", "song lyrics"],
        supported_intents=["write song lyrics", "노래 가사", "가사 써줘"],
        examples=[
            "노래 가사 써줘",
            "노래 가사",
            "JPOP 가사",
            "퇴사하고 다시 시작하는 이야기",
            "Jarvis 주제로 노래 가사",
        ],
        input_mode="text",
        input_prefixes=["creator lyrics", "lyrics", "song lyrics", "노래 가사", "가사"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a structured lyrics asset."""
        idea = default_idea(str(input_data.get("text", "")).strip())
        language = str(input_data.get("language", "")).strip() or detect_language(idea)
        genre = str(input_data.get("genre", "")).strip() or "J-pop rock"
        mood = str(input_data.get("mood", "")).strip() or "hopeful"
        vocal_style = str(input_data.get("vocal_style", "")).strip() or "female vocal"
        title = build_lyrics_title(idea, language)

        lyrics = build_korean_lyrics(idea) if language == "ko" else build_english_lyrics(idea)

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                **asset_header(idea, "lyrics"),
                "title": title,
                "idea": idea,
                "genre": genre,
                "mood": mood,
                "language": language,
                "vocal_style": vocal_style,
                "lyrics": lyrics,
            },
        )


def build_lyrics_title(idea, language):
    """Build a deterministic lyrics title."""
    if language == "ko":
        return "다시 시작하는 노래"

    return "Start Again"


def build_korean_lyrics(idea):
    """Build Korean draft lyrics."""
    return "\n".join(
        [
            "[Verse 1]",
            f"{idea} 그 길 위에 서서",
            "흔들린 마음을 다시 묶어",
            "작은 불빛 하나 품고 걸어가",
            "",
            "[Chorus]",
            "다시 시작해, 아직 끝이 아니야",
            "넘어진 자리에서 하늘을 봐",
            "오늘의 눈물이 내일의 리듬이 돼",
            "나는 다시 나를 믿어",
        ]
    )


def build_english_lyrics(idea):
    """Build English draft lyrics."""
    return "\n".join(
        [
            "[Verse 1]",
            f"I carried {idea} through the rain",
            "A quiet spark inside my chest",
            "Step by step I breathe again",
            "",
            "[Chorus]",
            "I start again, I rise tonight",
            "Turning scars into morning light",
            "If I fall, I learn to fly",
            "I start again, still alive",
        ]
    )
