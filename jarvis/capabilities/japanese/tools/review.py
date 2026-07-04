from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class JapaneseReviewTool:
    """Review recently learned Japanese expressions."""

    metadata = ToolMetadata(
        name="japanese_review",
        description="Review recently learned Japanese expressions from memory.",
        domain="japanese",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="japanese",
        aliases=["japanese review", "jp review", "review japanese"],
        supported_intents=["review japanese", "recent japanese expressions"],
        examples=["일본어 복습", "japanese review", "review japanese expressions"],
        input_mode="none",
        input_prefixes=["japanese review", "jp review", "review japanese"],
        route_confidence=0.78,
    )

    def __init__(self, memory_manager=None):
        """Create a review tool with optional long-term memory access."""
        self.memory_manager = memory_manager

    def execute(self, input_data):
        """Return recent Japanese memories or fallback guidance."""
        if self.memory_manager is not None:
            memories = self.memory_manager.find_by_tag("japanese")

            if len(memories) == 0:
                memories = self.memory_manager.search("japanese")

            if len(memories) > 0:
                return ToolResult(
                    tool_name=self.metadata.name,
                    success=True,
                    output=[memory.to_dict() for memory in memories[:5]],
                )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=(
                "No Japanese review memory yet. Save expressions with the japanese tag, "
                "then ask for japanese review again."
            ),
        )
