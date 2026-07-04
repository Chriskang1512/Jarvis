from jarvis.capabilities.creator.tools.common import asset_header, default_idea, title_case_slug
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class CreatorTitleTool:
    """Generate creative titles."""

    metadata = ToolMetadata(
        name="creator_title",
        description="Generate multiple titles for songs or videos.",
        domain="creator",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="creator",
        aliases=["creator title", "title ideas", "song title"],
        supported_intents=["generate title", "노래 제목", "유튜브 제목", "감성 제목"],
        examples=["노래 제목", "유튜브 제목", "감성 제목", "퇴사 후 다시 시작 제목"],
        input_mode="text",
        input_prefixes=["creator title", "title ideas", "song title", "노래 제목", "유튜브 제목", "제목"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return title candidates."""
        idea = default_idea(str(input_data.get("text", "")).strip())
        seed = title_case_slug(idea)
        titles = [
            f"{seed}",
            "다시 시작하는 밤",
            "넘어진 자리에서 피는 노래",
            "Start Again, Shine Again",
            "오늘을 건너 내일로",
            "퇴사 후 다시 켠 불빛",
            "Hope Runs Back To Me",
            "아직 끝나지 않은 우리",
            "New Game, Same Heart",
            "작은 용기의 엔딩곡",
        ]

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                **asset_header(idea, "title"),
                "idea": idea,
                "titles": titles[:10],
            },
        )
