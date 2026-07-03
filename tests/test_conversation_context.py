import unittest

from jarvis.chat import ChatService, PromptBuilder, create_default_prompt_profile
from jarvis.config.loader import create_config_from_dict
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.memory import ConversationContext
from jarvis.voice import create_voice_session


class CapturingProvider:
    """Test provider that records prompts."""

    def __init__(self):
        """Create a provider with an empty prompt list."""
        self.prompts = []

    def generate_reply(self, message):
        """Record a prompt and return a deterministic reply."""
        self.prompts.append(message)
        return f"reply {len(self.prompts)}"


class TestConversationContext(unittest.TestCase):
    """Test short-term conversation memory."""

    def test_conversation_context_keeps_recent_turns(self):
        """Check that the context keeps a bounded turn buffer."""
        context = ConversationContext(max_turns=2)

        context.add_turn("one", "reply one")
        context.add_turn("two", "reply two")
        context.add_turn("three", "reply three")

        history = context.build_history()
        self.assertNotIn("one", history)
        self.assertIn("two", history)
        self.assertIn("three", history)

    def test_config_sets_conversation_window(self):
        """Check that config can tune the conversation window."""
        config = create_config_from_dict(
            {
                "conversation": {
                    "max_turns": 4,
                    "max_tokens": 800,
                }
            }
        )

        self.assertEqual(config.conversation.max_turns, 4)
        self.assertEqual(config.conversation.max_tokens, 800)

    def test_voice_session_owns_conversation_context(self):
        """Check that conversation context belongs to the active voice session."""
        voice_session = create_voice_session(max_turns=4, max_tokens=800)

        self.assertIsInstance(voice_session.conversation_context, ConversationContext)
        self.assertEqual(voice_session.conversation_context.max_turns, 4)
        self.assertEqual(voice_session.conversation_context.max_tokens, 800)

    def test_chat_service_can_use_voice_session_context(self):
        """Check that ChatService uses VoiceSession as the context root."""
        provider = CapturingProvider()
        voice_session = create_voice_session(max_turns=3, max_tokens=800)
        service = ChatService(
            provider=provider,
            prompt_builder=PromptBuilder(create_default_prompt_profile()),
            voice_session=voice_session,
        )

        service.generate_reply("hello")

        self.assertEqual(len(voice_session.conversation_context.get_recent_turns()), 1)
        self.assertIs(service.conversation_context, voice_session.conversation_context)

    def test_chat_service_injects_recent_history(self):
        """Check that ChatService injects prior turns into the next prompt."""
        provider = CapturingProvider()
        context = ConversationContext(max_turns=3)
        service = ChatService(
            provider=provider,
            prompt_builder=PromptBuilder(create_default_prompt_profile()),
            conversation_context=context,
        )

        service.generate_reply("hello")
        service.generate_reply("what did I just say?")

        self.assertNotIn("Conversation History", provider.prompts[0])
        self.assertIn("Conversation History", provider.prompts[1])
        self.assertIn("User: hello", provider.prompts[1])
        self.assertIn("Assistant: reply 1", provider.prompts[1])
        self.assertIn("User Message:\nwhat did I just say?", provider.prompts[1])

    def test_conversation_diagnostics_events(self):
        """Check that conversation lifecycle events are published."""
        provider = CapturingProvider()
        diagnostics = DiagnosticsCollector()
        service = ChatService(
            provider=provider,
            prompt_builder=PromptBuilder(create_default_prompt_profile()),
            diagnostics_collector=diagnostics,
        )

        service.generate_reply("hello")
        service.generate_reply("continue")
        service.finish_conversation()

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("conversation.started", messages)
        self.assertIn("conversation.updated", messages)
        self.assertIn("conversation.context.injected", messages)
        self.assertIn("conversation.finished", messages)


if __name__ == "__main__":
    unittest.main()
