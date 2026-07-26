import unittest

from jarvis.config.loader import create_config_from_dict
from jarvis.input import InputManager, InputModality, InputSource
from jarvis.wake import (
    ApiWakeProvider,
    ClapDetector,
    ClapWakeProvider,
    KeyboardWakeProvider,
    MicrophoneWakeWordProvider,
    MobileWakeProvider,
    TouchPortalWakeProvider,
    WakeManager,
    WakeMethod,
    WakeProfile,
    WakeSettings,
    WakeWordProvider,
)
from jarvis.wake.voice import SpeechSegmenter
from jarvis.voice.wake_word import WakeWordListener
from unittest.mock import patch


class TestInputManager(unittest.TestCase):
    def test_envelope_redacts_content_by_default(self):
        envelope = InputManager().create(
            InputSource.CLIPBOARD,
            InputModality.TEXT,
            content="private clipboard text",
        )

        serialized = envelope.to_dict()

        self.assertNotIn("content", serialized)
        self.assertEqual(len(serialized["content_fingerprint"]), 64)
        self.assertEqual(
            envelope.to_dict(include_content=True)["content"],
            "private clipboard text",
        )

    def test_envelope_carries_wake_method_without_wake_payload(self):
        provider = ApiWakeProvider()
        provider.trigger({"remote_request_id": "request-1"})
        wake_event = provider.poll()

        envelope = InputManager().create(
            InputSource.VOICE,
            InputModality.AUDIO,
            wake_event=wake_event,
        )

        self.assertEqual(envelope.wake_method, WakeMethod.API.value)
        self.assertEqual(envelope.metadata["wake_provider"], "api")
        self.assertNotIn("remote_request_id", envelope.metadata)


class TestClapDetector(unittest.TestCase):
    def test_two_impulses_wake_without_stt(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertTrue(detector.process(impulse, 1.35))

    def test_sustained_loud_audio_is_not_a_clap(self):
        detector = ClapDetector()
        sustained = [0.7] * 100

        self.assertFalse(detector.process(sustained, 1.0))
        self.assertFalse(detector.process(sustained, 1.4))

    def test_late_second_clap_starts_a_new_pair(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertFalse(detector.process(impulse, 2.0))
        self.assertTrue(detector.process(impulse, 2.3))


class TestWakeProvidersAndManager(unittest.TestCase):
    def test_profile_priority_selects_clap_before_voice(self):
        clap = ClapWakeProvider()
        voice = WakeWordProvider()
        clap.trigger()
        voice.feed_text("헤이 자비스")
        manager = WakeManager((voice, clap))

        event = manager.wait(timeout=0.01)

        self.assertEqual(event.method, WakeMethod.CLAP)

    def test_disabled_method_is_ignored(self):
        clap = ClapWakeProvider()
        voice = WakeWordProvider()
        clap.trigger()
        voice.feed_text("자비스")
        profile = WakeProfile(
            priority=(WakeMethod.CLAP, WakeMethod.VOICE),
            enabled=(WakeMethod.VOICE,),
        )
        manager = WakeManager((clap, voice), WakeSettings(profile=profile))

        event = manager.wait(timeout=0.01)

        self.assertEqual(event.method, WakeMethod.VOICE)

    def test_voice_provider_supports_english_and_korean_phrases(self):
        for phrase in ("hey jarvis", "헤이 자비스", "자비스"):
            provider = WakeWordProvider()
            self.assertTrue(provider.feed_text(phrase))
            self.assertEqual(provider.poll().method, WakeMethod.VOICE)

    def test_voice_provider_ignores_transcription_punctuation_and_spacing(self):
        provider = WakeWordProvider()

        self.assertTrue(provider.feed_text("헤이, 자비스."))
        self.assertEqual(provider.poll().metadata["phrase"], "헤이, 자비스.")

    def test_microphone_voice_provider_transcribes_segment_and_wakes(self):
        monitor = FakeSharedMonitor()
        provider = MicrophoneWakeWordProvider(
            ("hey jarvis", "헤이 자비스", "자비스"),
            transcribe=lambda audio: "자비스." if audio else "",
            monitor=monitor,
        )

        provider.start()
        provider.segmenter.on_segment(b"wav")
        for _ in range(50):
            event = provider.poll()
            if event is not None:
                break
            __import__("time").sleep(0.01)
        provider.stop()

        self.assertIsNotNone(event)
        self.assertEqual(event.method, WakeMethod.VOICE)

    def test_speech_segmenter_emits_short_wav_after_silence(self):
        segments = []
        segmenter = SpeechSegmenter(segments.append)
        speech = [0.02] * 800
        silence = [0.0] * 800

        segmenter.process(speech, 1.00)
        segmenter.process(speech, 1.05)
        for index in range(12):
            segmenter.process(silence, 1.10 + index * 0.05)

        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0].startswith(b"RIFF"))

    def test_keyboard_hotkey_only_triggers_on_exact_binding(self):
        provider = KeyboardWakeProvider("ctrl+space")

        self.assertFalse(provider.press("alt+j"))
        self.assertTrue(provider.press("CTRL+SPACE"))
        self.assertEqual(provider.poll().method, WakeMethod.KEYBOARD)

    def test_external_trigger_stubs_share_provider_contract(self):
        for provider in (
            TouchPortalWakeProvider(),
            MobileWakeProvider(),
            ApiWakeProvider(),
        ):
            provider.trigger()
            event = provider.poll()
            self.assertIsNotNone(event)
            self.assertEqual(event.provider_id, provider.provider_id)

    def test_manager_starts_and_stops_clap_audio_monitor(self):
        monitor = FakeClapMonitor()
        clap = ClapWakeProvider(monitor=monitor)
        monitor.provider = clap
        profile = WakeProfile(
            priority=(WakeMethod.CLAP,),
            enabled=(WakeMethod.CLAP,),
        )
        manager = WakeManager((clap,), WakeSettings(profile=profile))

        event = manager.wait(timeout=0.05)

        self.assertEqual(event.method, WakeMethod.CLAP)
        self.assertTrue(monitor.started)
        self.assertTrue(monitor.stopped)


class TestWakeConfiguration(unittest.TestCase):
    def test_loader_builds_profile_settings_without_config_file_changes(self):
        config = create_config_from_dict(
            {
                "wake": {
                    "primary": "voice",
                    "methods": ["voice", "keyboard"],
                    "voice_phrases": ["jarvis", "자비스"],
                    "keyboard_hotkey": "alt+j",
                }
            }
        )

        self.assertEqual(config.wake.primary, "voice")
        self.assertEqual(config.wake.methods, ("voice", "keyboard"))
        self.assertEqual(config.wake.voice_phrases, ("jarvis", "자비스"))
        self.assertEqual(config.wake.keyboard_hotkey, "alt+j")

    def test_legacy_listener_accepts_korean_alias(self):
        listener = WakeWordListener("hey jarvis", aliases=("헤이 자비스", "자비스"))

        with patch("builtins.input", return_value="자비스"):
            self.assertEqual(listener.wait_for_wake_word(), "자비스")


class FakeClapMonitor:
    def __init__(self):
        self.provider = None
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        impulse = [0.0] * 99 + [1.0]
        self.provider.feed_audio(impulse, 1.0)
        self.provider.feed_audio(impulse, 1.3)
        return True

    def stop(self):
        self.stopped = True


class FakeSharedMonitor:
    def __init__(self):
        self.listeners = []

    def add_listener(self, listener):
        self.listeners.append(listener)

    def start(self):
        return True

    def stop(self):
        return None


if __name__ == "__main__":
    unittest.main()
