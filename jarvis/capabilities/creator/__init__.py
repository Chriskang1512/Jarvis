from jarvis.capabilities.creator.metadata import CREATOR_CAPABILITY_METADATA
from jarvis.capabilities.creator.tools import (
    CreatorDescriptionTool,
    CreatorLyricsTool,
    CreatorMusicPromptTool,
    CreatorSongPackageTool,
    CreatorTitleTool,
)


class CreatorCapability:
    """Capability skeleton for creator workflows."""

    metadata = CREATOR_CAPABILITY_METADATA

    def get_tools(self):
        """Return tools owned by this capability."""
        return [
            CreatorLyricsTool(),
            CreatorMusicPromptTool(),
            CreatorTitleTool(),
            CreatorDescriptionTool(),
            CreatorSongPackageTool(),
        ]


def create_capability():
    """Create the Creator capability."""
    return CreatorCapability()
