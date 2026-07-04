import unittest

from jarvis.brain import BrainToolRouter
from jarvis.capabilities import CapabilityLoader
from jarvis.tools import ToolDispatcher, ToolRequest, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry


class TestCreatorCapability(unittest.TestCase):
    """Test Creator Capability Alpha."""

    def test_creator_capability_is_discovered(self):
        """Check the Creator capability is discovered by the loader."""
        registry = CapabilityLoader().load()

        self.assertTrue(registry.exists("creator"))

    def test_creator_tools_are_registered(self):
        """Check Creator capability registers all alpha tools."""
        capability_registry = CapabilityLoader().load()
        tool_registry = ToolRegistry()
        capability_registry.register_tools(tool_registry)

        self.assertTrue(tool_registry.exists("creator_lyrics"))
        self.assertTrue(tool_registry.exists("creator_music_prompt"))
        self.assertTrue(tool_registry.exists("creator_title"))
        self.assertTrue(tool_registry.exists("creator_description"))
        self.assertTrue(tool_registry.exists("creator_song_package"))

    def test_brain_routes_lyrics_request(self):
        """Check Brain routes lyrics requests through metadata."""
        request = BrainToolRouter().plan(
            "노래 가사 써줘",
            registry=create_creator_tool_registry(),
        )

        self.assertEqual(request.tool_name, "creator_lyrics")

    def test_brain_routes_music_prompt_request(self):
        """Check Brain routes music prompt requests through metadata."""
        request = BrainToolRouter().plan(
            "music prompt j-pop hopeful female vocal",
            registry=create_creator_tool_registry(),
        )

        self.assertEqual(request.tool_name, "creator_music_prompt")

    def test_brain_routes_title_request(self):
        """Check Brain routes title requests through metadata."""
        request = BrainToolRouter().plan(
            "퇴사 후 다시 시작 제목",
            registry=create_creator_tool_registry(),
        )

        self.assertEqual(request.tool_name, "creator_title")

    def test_brain_routes_description_request(self):
        """Check Brain routes description requests through metadata."""
        request = BrainToolRouter().plan(
            "youtube description",
            registry=create_creator_tool_registry(),
        )

        self.assertEqual(request.tool_name, "creator_description")

    def test_brain_routes_song_package_request(self):
        """Check Brain routes song package requests through metadata."""
        request = BrainToolRouter().plan(
            "song package",
            registry=create_creator_tool_registry(),
        )

        self.assertEqual(request.tool_name, "creator_song_package")

    def test_lyrics_tool_returns_contract(self):
        """Check lyrics tool returns stable output contract."""
        result = ToolDispatcher(registry=create_creator_tool_registry()).execute(
            ToolRequest(
                tool_name="creator_lyrics",
                input_data={"text": "퇴사하고 다시 시작하는 이야기"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["subdomain"], "song")
        self.assertEqual(result.output["asset"], "lyrics")
        self.assertIn("project", result.output)
        self.assertIn("title", result.output)
        self.assertIn("genre", result.output)
        self.assertIn("mood", result.output)
        self.assertIn("lyrics", result.output)

    def test_music_prompt_tool_returns_contract(self):
        """Check music prompt tool returns stable output contract."""
        result = ToolDispatcher(registry=create_creator_tool_registry()).execute(
            ToolRequest(
                tool_name="creator_music_prompt",
                input_data={"text": "j-pop hopeful female vocal"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["subdomain"], "song")
        self.assertEqual(result.output["asset"], "music_prompt")
        self.assertIn("genre", result.output)
        self.assertIn("tempo", result.output)
        self.assertIn("vocal", result.output)
        self.assertIn("prompt", result.output)
        self.assertEqual(result.output["vocal"], "female vocal")

    def test_title_tool_returns_ten_titles(self):
        """Check title tool returns title candidates."""
        result = ToolDispatcher(registry=create_creator_tool_registry()).execute(
            ToolRequest(
                tool_name="creator_title",
                input_data={"text": "퇴사 후 다시 시작"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["asset"], "title")
        self.assertEqual(len(result.output["titles"]), 10)

    def test_description_tool_returns_contract(self):
        """Check description tool returns a description field."""
        result = ToolDispatcher(registry=create_creator_tool_registry()).execute(
            ToolRequest(tool_name="creator_description", input_data={"text": "youtube description"})
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["asset"], "description")
        self.assertIn("description", result.output)

    def test_song_package_tool_returns_composed_contract(self):
        """Check song package is local Creator-only orchestration."""
        result = ToolDispatcher(registry=create_creator_tool_registry()).execute(
            ToolRequest(tool_name="creator_song_package", input_data={"text": "퇴사 후 다시 시작"})
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["subdomain"], "song")
        self.assertEqual(result.output["asset"], "song_package")
        self.assertIn("project", result.output)
        self.assertIn("assets", result.output)
        self.assertIn("lyrics", result.output)
        self.assertIn("music_prompt", result.output)
        self.assertIn("titles", result.output)
        self.assertIn("thumbnail_prompt", result.output)
        self.assertIn("description", result.output)
        self.assertIn("tags", result.output)
        self.assertIn("not the Multi Tool Planner", result.output["note"])

    def test_existing_japanese_finance_core_routes_still_pass(self):
        """Check Creator does not break existing capability and Core routes."""
        tool_registry = create_default_tool_registry()
        capability_registry = CapabilityLoader().load()
        capability_registry.register_tools(tool_registry)
        router = BrainToolRouter()

        self.assertEqual(router.plan("reply to aya", registry=tool_registry).tool_name, "japanese_reply")
        self.assertEqual(router.plan("finance compound", registry=tool_registry).tool_name, "finance_compound")
        self.assertEqual(router.plan("calculate 2 + 2", registry=tool_registry).tool_name, "calculator")


def create_creator_tool_registry():
    """Create a ToolRegistry with Creator capability tools."""
    capability_registry = CapabilityLoader().load()
    tool_registry = ToolRegistry()
    capability_registry.register_tools(tool_registry)
    return tool_registry


if __name__ == "__main__":
    unittest.main()
