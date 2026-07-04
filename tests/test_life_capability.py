import unittest

from jarvis.brain import BrainToolRouter
from jarvis.capabilities import CapabilityLoader
from jarvis.capabilities.life import LifeCapability
from jarvis.memory_store import InMemoryStore, MemoryManager
from jarvis.tools import ToolDispatcher, ToolRequest, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry


class TestLifeCapability(unittest.TestCase):
    """Test Life Capability Alpha."""

    def test_life_capability_is_discovered(self):
        """Check the Life capability is discovered by the loader."""
        registry = CapabilityLoader().load()

        self.assertTrue(registry.exists("life"))

    def test_life_tools_are_registered(self):
        """Check Life capability registers all alpha tools."""
        tool_registry = create_life_tool_registry()

        self.assertTrue(tool_registry.exists("life_todo"))
        self.assertTrue(tool_registry.exists("life_reminder"))
        self.assertTrue(tool_registry.exists("life_routine"))
        self.assertTrue(tool_registry.exists("life_habit"))
        self.assertTrue(tool_registry.exists("life_reflection"))

    def test_brain_routes_life_todo_request(self):
        """Check Brain routes todo requests through metadata."""
        request = BrainToolRouter().plan(
            "오늘 할 일 정리해줘",
            registry=create_life_tool_registry(),
        )

        self.assertEqual(request.tool_name, "life_todo")

    def test_brain_routes_life_reminder_request(self):
        """Check Brain routes reminder requests through metadata."""
        request = BrainToolRouter().plan(
            "내일 아침에 회고하라고 알려줘",
            registry=create_life_tool_registry(),
        )

        self.assertEqual(request.tool_name, "life_reminder")

    def test_brain_routes_life_routine_request(self):
        """Check Brain routes routine requests through metadata."""
        request = BrainToolRouter().plan(
            "아침 루틴 만들어줘",
            registry=create_life_tool_registry(),
        )

        self.assertEqual(request.tool_name, "life_routine")

    def test_brain_routes_life_habit_request(self):
        """Check Brain routes habit requests through metadata."""
        request = BrainToolRouter().plan(
            "매일 회고 습관 추적표 만들어줘",
            registry=create_life_tool_registry(),
        )

        self.assertEqual(request.tool_name, "life_habit")

    def test_brain_routes_life_reflection_request(self):
        """Check Brain routes reflection requests through metadata."""
        request = BrainToolRouter().plan(
            "오늘 회고 정리해줘",
            registry=create_life_tool_registry(),
        )

        self.assertEqual(request.tool_name, "life_reflection")

    def test_reminder_returns_scheduler_ready_contract(self):
        """Check reminder does not schedule but returns Scheduler-ready output."""
        result = ToolDispatcher(registry=create_life_tool_registry()).execute(
            ToolRequest(
                tool_name="life_reminder",
                input_data={"text": "내일 아침에 회고하라고 알려줘"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["tool"], "life_reminder")
        self.assertEqual(result.output["recommended_time"], "tomorrow morning")
        self.assertEqual(result.output["priority"], "normal")
        self.assertTrue(result.output["ready_for_scheduler"])
        self.assertFalse(result.output["scheduled"])

    def test_reflection_returns_contract(self):
        """Check reflection returns the requested review sections."""
        result = ToolDispatcher(registry=create_life_tool_registry()).execute(
            ToolRequest(
                tool_name="life_reflection",
                input_data={"text": "오늘 회고 정리해줘"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["tool"], "life_reflection")
        self.assertIn("summary", result.output)
        self.assertIn("wins", result.output)
        self.assertIn("problems", result.output)
        self.assertIn("ideas", result.output)
        self.assertIn("next_actions", result.output)
        self.assertIsInstance(result.output["wins"], list)
        self.assertIsInstance(result.output["next_actions"], list)

    def test_reflection_reads_memory_when_available(self):
        """Check reflection can read recent Memory without owning Memory."""
        memory_manager = MemoryManager(store=InMemoryStore())
        memory_manager.remember(
            "Jarvis v0.4 alpha freeze completed.",
            category="project",
            title="Alpha freeze",
            tags=["jarvis", "reflection"],
        )
        capability = LifeCapability(memory_manager=memory_manager)
        tool_registry = ToolRegistry()

        for tool in capability.get_tools():
            tool_registry.register(tool)

        result = ToolDispatcher(registry=tool_registry).execute(
            ToolRequest(tool_name="life_reflection", input_data={"text": "자비스 회고"})
        )

        self.assertTrue(result.success)
        self.assertTrue(result.output["memory_used"])
        self.assertEqual(result.output["memory"][0]["title"], "Alpha freeze")

    def test_existing_capability_and_core_routes_still_pass(self):
        """Check Life does not break Japanese, Finance, Creator, Hotel, or Core."""
        tool_registry = create_default_tool_registry()
        capability_registry = CapabilityLoader().load()
        capability_registry.register_tools(tool_registry)
        router = BrainToolRouter()

        self.assertEqual(router.plan("reply to aya", registry=tool_registry).tool_name, "japanese_reply")
        self.assertEqual(router.plan("finance compound", registry=tool_registry).tool_name, "finance_compound")
        self.assertEqual(router.plan("song package", registry=tool_registry).tool_name, "creator_song_package")
        self.assertEqual(router.plan("호텔 스케줄 짜줘", registry=tool_registry).tool_name, "hotel_schedule_planner")
        self.assertEqual(router.plan("calculate 2 + 2", registry=tool_registry).tool_name, "calculator")
        self.assertEqual(router.plan("what time is it", registry=tool_registry).tool_name, "time")


def create_life_tool_registry():
    """Create a ToolRegistry with Life capability tools."""
    capability_registry = CapabilityLoader().load()
    tool_registry = ToolRegistry()
    capability_registry.register_tools(tool_registry)
    return tool_registry


if __name__ == "__main__":
    unittest.main()
