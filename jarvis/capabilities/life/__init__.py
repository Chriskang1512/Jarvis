from jarvis.capabilities.life.metadata import LIFE_CAPABILITY_METADATA
from jarvis.capabilities.life.tools import (
    LifeHabitTool,
    LifeReflectionTool,
    LifeReminderTool,
    LifeRoutineTool,
    LifeTodoTool,
)


class LifeCapability:
    """Personal life capability close to memory, routines, and daily planning."""

    metadata = LIFE_CAPABILITY_METADATA

    def __init__(self, memory_manager=None):
        """Create Life capability with optional memory access."""
        self.memory_manager = memory_manager

    def get_tools(self):
        """Return tools owned by this capability."""
        return [
            LifeTodoTool(),
            LifeReminderTool(),
            LifeRoutineTool(),
            LifeHabitTool(),
            LifeReflectionTool(memory_manager=self.memory_manager),
        ]


def create_capability(memory_manager=None):
    """Create the Life capability."""
    return LifeCapability(memory_manager=memory_manager)
