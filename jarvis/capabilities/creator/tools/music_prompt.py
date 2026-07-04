from jarvis.capabilities.creator.tools.common import asset_header, default_idea
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class CreatorMusicPromptTool:
    """Generate prompts for AI music generators."""

    metadata = ToolMetadata(
        name="creator_music_prompt",
        description="Generate a prompt for AI music generators such as Suno, Udio, or Stable Audio.",
        domain="creator",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="creator",
        aliases=["creator music prompt", "music prompt", "suno prompt", "udio prompt"],
        supported_intents=["music prompt", "ai music prompt", "음악 프롬프트"],
        examples=[
            "music prompt j-pop hopeful female vocal",
            "J-pop Anime Ending Hopeful Female Vocal 120 BPM",
            "Suno 프롬프트",
            "음악 프롬프트 만들어줘",
        ],
        input_mode="text",
        input_prefixes=["creator music prompt", "music prompt", "suno prompt", "udio prompt", "음악 프롬프트"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a structured music prompt asset."""
        text = default_idea(str(input_data.get("text", "")).strip())
        genre = str(input_data.get("genre", "")).strip() or detect_genre(text)
        mood = str(input_data.get("mood", "")).strip() or detect_mood(text)
        vocal = str(input_data.get("vocal", "")).strip() or detect_vocal(text)
        tempo = str(input_data.get("tempo", "")).strip() or detect_tempo(text)
        model_targets = ["Suno", "Udio", "Stable Audio"]
        prompt = (
            f"{genre}, {mood}, {vocal}, modern production, anime ending energy, "
            f"{tempo}, emotional chorus, clean mix, uplifting arrangement"
        )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                **asset_header(text, "music_prompt"),
                "genre": genre,
                "mood": mood,
                "tempo": tempo,
                "vocal": vocal,
                "target_models": model_targets,
                "prompt": prompt,
            },
        )


def detect_genre(text):
    """Detect a simple genre from input."""
    lowered = text.lower()
    if "j-pop" in lowered or "jpop" in lowered:
        return "J-pop rock"
    if "lofi" in lowered:
        return "lo-fi pop"
    if "rock" in lowered:
        return "modern rock"
    return "J-pop rock"


def detect_mood(text):
    """Detect a simple mood from input."""
    lowered = text.lower()
    if "sad" in lowered or "melancholy" in lowered:
        return "melancholic but hopeful"
    if "hope" in lowered or "희망" in text:
        return "hopeful"
    return "hopeful"


def detect_vocal(text):
    """Detect a simple vocal style from input."""
    lowered = text.lower()
    if "female" in lowered or "여성" in text:
        return "female vocal"
    if "male" in lowered:
        return "male vocal"
    return "female vocal"


def detect_tempo(text):
    """Detect a simple tempo from input."""
    lowered = text.lower()
    if "bpm" in lowered:
        parts = lowered.split()
        for index, part in enumerate(parts):
            if part.endswith("bpm"):
                return part.upper()
            if part.isdigit() and index + 1 < len(parts) and parts[index + 1] == "bpm":
                return f"{part} BPM"
    return "120 BPM"
