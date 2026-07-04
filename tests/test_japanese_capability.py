import unittest

from jarvis.brain import BrainToolRouter
from jarvis.capabilities import CapabilityLoader
from jarvis.capabilities.japanese import JapaneseCapability
from jarvis.memory_store import InMemoryStore, MemoryManager
from jarvis.tools import ToolDispatcher, ToolRequest, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry


class TestJapaneseCapability(unittest.TestCase):
    """Test Japanese Capability Alpha."""

    def test_japanese_capability_is_discovered(self):
        """Check the Japanese capability is discovered by the loader."""
        registry = CapabilityLoader().load()

        self.assertTrue(registry.exists("japanese"))

    def test_japanese_tools_are_registered(self):
        """Check Japanese capability registers all alpha tools."""
        capability_registry = CapabilityLoader().load()
        tool_registry = ToolRegistry()
        capability_registry.register_tools(tool_registry)

        self.assertTrue(tool_registry.exists("japanese_translate"))
        self.assertTrue(tool_registry.exists("japanese_grammar"))
        self.assertTrue(tool_registry.exists("japanese_reply"))
        self.assertTrue(tool_registry.exists("japanese_review"))

    def test_brain_routes_japanese_grammar_request(self):
        """Check Brain routes grammar requests through registry metadata."""
        tool_registry = create_japanese_tool_registry()
        request = BrainToolRouter().plan(
            "japanese grammar しらない vs わからない",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "japanese_grammar")
        self.assertEqual(request.input_data["text"], "しらない vs わからない")

    def test_brain_routes_japanese_reply_request(self):
        """Check Brain routes reply requests through registry metadata."""
        tool_registry = create_japanese_tool_registry()
        request = BrainToolRouter().plan(
            "japanese reply ユイ 오늘도 수고했어",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "japanese_reply")
        self.assertIn("ユイ", request.input_data["text"])

    def test_brain_routes_from_tool_metadata_examples(self):
        """Check Brain can route through ToolMetadata examples."""
        tool_registry = create_japanese_tool_registry()
        request = BrainToolRouter().plan("reply to aya", registry=tool_registry)

        self.assertEqual(request.tool_name, "japanese_reply")

    def test_ambiguous_japanese_chat_falls_back_to_llm(self):
        """Check ambiguous Japanese-related chat does not force a tool."""
        tool_registry = create_japanese_tool_registry()
        request = BrainToolRouter().plan(
            "Japanese sounds beautiful today",
            registry=tool_registry,
        )

        self.assertIsNone(request)

    def test_translate_tool_returns_learning_fields(self):
        """Check translate output includes the required learning fields."""
        tool_registry = create_japanese_tool_registry()
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="japanese_translate",
                input_data={"text": "안녕하세요"},
            )
        )

        self.assertTrue(result.success)
        self.assertIn("hiragana", result.output)
        self.assertIn("japanese", result.output)
        self.assertIn("pronunciation", result.output)
        self.assertIn("meaning", result.output)

    def test_brain_routes_short_translate_request(self):
        """Check prefix-light translate requests route to Japanese translate."""
        tool_registry = create_japanese_tool_registry()
        request = BrainToolRouter().plan("translate 안녕하세요", registry=tool_registry)

        self.assertEqual(request.tool_name, "japanese_translate")

    def test_grammar_tool_explains_known_difference(self):
        """Check grammar tool explains supported comparison pairs."""
        tool_registry = create_japanese_tool_registry()
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="japanese_grammar",
                input_data={"text": "たのしそう vs たのしみ"},
            )
        )

        self.assertTrue(result.success)
        self.assertIn("looks fun", result.output)

    def test_reply_tool_respects_preferred_names(self):
        """Check reply tool respects Aya and Yui names."""
        tool_registry = create_japanese_tool_registry()
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(
            ToolRequest(
                tool_name="japanese_reply",
                input_data={"text": "ユイ 오늘도 수고했어"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["name"], "ユイ")
        self.assertIn("ユイ", result.output["japanese"])

    def test_review_tool_reads_memory_when_available(self):
        """Check review tool returns recent Japanese memories."""
        memory_manager = MemoryManager(store=InMemoryStore())
        memory_manager.remember(
            "ありがとう means thank you.",
            category="fact",
            tags=["japanese"],
        )
        capability = JapaneseCapability(memory_manager=memory_manager)
        tool_registry = ToolRegistry()

        for tool in capability.get_tools():
            tool_registry.register(tool)

        dispatcher = ToolDispatcher(registry=tool_registry)
        result = dispatcher.execute(ToolRequest(tool_name="japanese_review"))

        self.assertTrue(result.success)
        self.assertEqual(result.output[0]["content"], "ありがとう means thank you.")

    def test_review_tool_returns_fallback_when_memory_is_empty(self):
        """Check review tool gives guidance when memory has no Japanese entries."""
        tool_registry = create_japanese_tool_registry()
        dispatcher = ToolDispatcher(registry=tool_registry)

        result = dispatcher.execute(ToolRequest(tool_name="japanese_review"))

        self.assertTrue(result.success)
        self.assertIn("No Japanese review memory yet", result.output)

    def test_existing_core_routes_still_pass_with_japanese_capability(self):
        """Check existing calculator, time, and diagnostics routes still work."""
        tool_registry = create_default_tool_registry()
        capability_registry = CapabilityLoader().load()
        capability_registry.register_tools(tool_registry)
        router = BrainToolRouter()

        self.assertEqual(
            router.plan("calculate 1 + 2", registry=tool_registry).tool_name,
            "calculator",
        )
        self.assertEqual(
            router.plan("what time is it", registry=tool_registry).tool_name,
            "time",
        )
        self.assertEqual(
            router.plan("health check", registry=tool_registry).tool_name,
            "diagnostics",
        )


def create_japanese_tool_registry():
    """Create a ToolRegistry with Japanese capability tools."""
    capability_registry = CapabilityLoader().load()
    tool_registry = ToolRegistry()
    capability_registry.register_tools(tool_registry)
    return tool_registry


if __name__ == "__main__":
    unittest.main()
