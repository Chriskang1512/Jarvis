from jarvis.capabilities.creator.tools.description import CreatorDescriptionTool
from jarvis.capabilities.creator.tools.lyrics import CreatorLyricsTool
from jarvis.capabilities.creator.tools.common import asset_header, project_id_from_idea
from jarvis.capabilities.creator.tools.music_prompt import CreatorMusicPromptTool
from jarvis.capabilities.creator.tools.title import CreatorTitleTool
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class CreatorSongPackageTool:
    """Create a local song package from Creator tools."""

    metadata = ToolMetadata(
        name="creator_song_package",
        description="Generate lyrics, music prompt, titles, thumbnail prompt, description, and tags for one song idea.",
        domain="creator",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="creator",
        aliases=["creator song package", "song package", "song kit"],
        supported_intents=["song package", "complete song package", "노래 패키지"],
        examples=["song package", "creator song package 퇴사 후 다시 시작", "노래 패키지 만들어줘"],
        input_mode="text",
        input_prefixes=["creator song package", "song package", "song kit", "노래 패키지"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Run local Creator tools sequentially and return a package."""
        idea = str(input_data.get("text", "")).strip() or "퇴사 후 다시 시작"
        project = project_id_from_idea(idea, fallback="song_project")
        lyrics = CreatorLyricsTool().execute({"text": idea}).output
        music_prompt = CreatorMusicPromptTool().execute({"text": idea}).output
        title = CreatorTitleTool().execute({"text": idea}).output
        description = CreatorDescriptionTool().execute({"text": idea}).output
        thumbnail_prompt = (
            "Hopeful anime-style character standing at sunrise, city skyline, "
            "warm light, emotional comeback mood, clean thumbnail composition"
        )
        tags = ["AI Creator", "J-pop", "Hopeful", "Original Song", "Start Again"]

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                **asset_header(idea, "song_package", project=project),
                "idea": idea,
                "assets": {
                    "lyrics": lyrics,
                    "music_prompt": music_prompt,
                    "titles": title["titles"],
                    "thumbnail_prompt": thumbnail_prompt,
                    "description": description["description"],
                    "tags": tags,
                },
                "lyrics": lyrics,
                "music_prompt": music_prompt,
                "titles": title["titles"],
                "thumbnail_prompt": thumbnail_prompt,
                "description": description["description"],
                "tags": tags,
                "note": "Local Creator orchestration only. This is not the Multi Tool Planner.",
            },
        )
