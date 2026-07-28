import unittest
from types import SimpleNamespace

from jarvis.input import InputSource
from jarvis.runtime import JarvisRuntimeService
from jarvis.runtime import RuntimeBusyError


class FakePipeline:
    def __init__(self):
        self.voice_session = SimpleNamespace(session_id="WEB-SESSION")
        self.conversation_session = None
        self.last_input_envelope = None
        self.tts_provider = SimpleNamespace()
        self.calls = []

    def start_conversation_session(self):
        self.conversation_session = object()

    def process_follow_up_text(self, text, speak=True):
        self.calls.append((text, speak))
        return f"reply:{text}"


class FakeWakeManager:
    def __init__(self):
        self.paused = False
        self.calls = []

    def pause(self, reason):
        self.paused = True
        self.calls.append(("pause", reason))

    def resume(self, reason):
        self.paused = False
        self.calls.append(("resume", reason))


class TestJarvisRuntimeServiceInteraction(unittest.TestCase):
    def setUp(self):
        self.pipeline = FakePipeline()
        config = SimpleNamespace(
            stt=SimpleNamespace(openai_model="gpt-4o-transcribe", openai_language="ko"),
            tts=SimpleNamespace(response_format="wav"),
        )
        self.runtime = JarvisRuntimeService(self.pipeline, config)

    def test_text_uses_shared_input_envelope_and_pipeline(self):
        result = self.runtime.submit_text("오늘 일정 알려줘")
        self.assertEqual(result["text"], "reply:오늘 일정 알려줘")
        self.assertEqual(result["input"]["source"], "keyboard")
        self.assertEqual(result["input"]["modality"], "text")
        self.assertNotEqual(result["input"]["context"]["session_id"], "WEB-SESSION")
        self.assertTrue(result["input"]["context"]["session_id"])
        self.assertEqual(self.pipeline.calls, [("오늘 일정 알려줘", False)])
        self.runtime.finish_browser_playback(result["playback_token"])

    def test_voice_text_keeps_voice_source(self):
        result = self.runtime.submit_text("강릉 날씨", source=InputSource.VOICE)
        self.assertEqual(result["input"]["source"], "voice")
        self.runtime.finish_browser_playback(result["playback_token"])

    def test_empty_text_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            self.runtime.submit_text(" ")

    def test_wake_stays_paused_until_browser_playback_ack(self):
        wake = FakeWakeManager()
        config = SimpleNamespace(
            stt=SimpleNamespace(openai_model="gpt-4o-transcribe", openai_language="ko"),
            tts=SimpleNamespace(response_format="wav"),
        )
        runtime = JarvisRuntimeService(self.pipeline, config, wake_manager=wake)
        result = runtime.submit_text("일본어로 답해줘")
        self.assertTrue(wake.paused)
        self.assertEqual(wake.calls, [("pause", "runtime_owner:dashboard")])
        runtime.finish_browser_playback(result["playback_token"])
        self.assertFalse(wake.paused)
        self.assertEqual(wake.calls[-1], ("resume", "browser_ack"))

    def test_second_dashboard_turn_gets_busy_until_playback_finishes(self):
        first = self.runtime.submit_text("first")

        with self.assertRaises(RuntimeBusyError):
            self.runtime.submit_text("second")

        self.runtime.finish_browser_playback(first["playback_token"])
        second = self.runtime.submit_text("second")
        self.runtime.finish_browser_playback(second["playback_token"])


if __name__ == "__main__":
    unittest.main()
