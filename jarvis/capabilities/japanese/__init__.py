from jarvis.capabilities.japanese.metadata import JAPANESE_CAPABILITY_METADATA
from jarvis.capabilities.japanese.tools import (
    JapaneseGrammarTool,
    JapaneseReplyTool,
    JapaneseReviewTool,
    JapaneseTranslateTool,
)


class JapaneseCapability:
    """Capability skeleton for Japanese learning workflows."""

    metadata = JAPANESE_CAPABILITY_METADATA

    def __init__(self, memory_manager=None):
        """Create the Japanese capability."""
        self.memory_manager = memory_manager

    def get_tools(self):
        """Return tools owned by this capability."""
        return [
            JapaneseTranslateTool(),
            JapaneseGrammarTool(),
            JapaneseReplyTool(),
            JapaneseReviewTool(memory_manager=self.memory_manager),
        ]


def create_capability(memory_manager=None):
    """Create the Japanese capability."""
    return JapaneseCapability(memory_manager=memory_manager)
