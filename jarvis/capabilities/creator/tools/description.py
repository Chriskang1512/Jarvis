from jarvis.capabilities.creator.tools.common import asset_header, default_idea
from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class CreatorDescriptionTool:
    """Generate reusable descriptions for creative assets."""

    metadata = ToolMetadata(
        name="creator_description",
        description="Generate YouTube or song descriptions.",
        domain="creator",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="creator",
        aliases=["creator description", "youtube description", "song description"],
        supported_intents=["youtube description", "song description", "유튜브 설명"],
        examples=["youtube description", "유튜브 설명", "노래 설명", "description for hopeful song"],
        input_mode="text",
        input_prefixes=["creator description", "youtube description", "song description", "유튜브 설명", "노래 설명"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a structured description asset."""
        idea = default_idea(str(input_data.get("text", "")).strip())
        description_type = str(input_data.get("type", "")).strip() or infer_description_type(idea)
        description = (
            f"{idea}\n\n"
            "A hopeful creative piece about falling, breathing, and starting again. "
            "Built as a reusable Creator asset for lyrics, music prompts, and future publishing workflows.\n\n"
            "#AIcreator #JPop #Hopeful #OriginalSong"
        )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                **asset_header(idea, "description"),
                "type": description_type,
                "idea": idea,
                "description": description,
            },
        )


def infer_description_type(text):
    """Infer the description target."""
    lowered = text.lower()
    if "youtube" in lowered or "유튜브" in text:
        return "youtube"
    return "song"
