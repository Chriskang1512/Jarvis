import unittest
from threading import Event, Timer

from jarvis.config.loader import create_config_from_dict
from jarvis.input import (
    ActivationType,
    ClipboardInputProvider,
    InputManager,
    InputModality,
    InputSource,
    InputType,
    KeyboardInputProvider,
)
from jarvis.wake import (
    ApiWakeProvider,
    ClapDetector,
    ClapWakeProvider,
    SoundDeviceClapMonitor,
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
from jarvis.wake.voice import SpeechSegmenter, WakePhraseTranscriber
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

    def test_envelope_preserves_typed_activation_context(self):
        provider = WakeWordProvider()
        provider.feed_text("헤이 자비스")
        wake_event = provider.poll()

        envelope = InputManager().create(
            InputSource.VOICE,
            InputModality.TEXT,
            content="오늘 날씨",
            wake_event=wake_event,
            correlation_id="session-1",
        )

        activation = envelope.context.activation
        self.assertEqual(activation.activation_type, ActivationType.WAKE_WORD)
        self.assertEqual(activation.activation_provider, "wake_word")
        self.assertEqual(activation.activation_phrase, "헤이 자비스")
        self.assertEqual(activation.activation_id, wake_event.event_id)
        self.assertEqual(envelope.context.session_id, "session-1")

    def test_keyboard_and_clipboard_use_common_ingest_gate(self):
        manager = InputManager()
        keyboard = KeyboardInputProvider()
        clipboard = ClipboardInputProvider()
        keyboard.submit("status")
        clipboard.submit("private clipboard")

        keyboard_envelope = manager.ingest(keyboard)
        clipboard_envelope = manager.ingest(
            clipboard,
            input_type=InputType.CONTENT,
        )

        self.assertEqual(keyboard_envelope.source, InputSource.KEYBOARD)
        self.assertEqual(keyboard_envelope.metadata["input_provider"], "keyboard_text")
        self.assertEqual(clipboard_envelope.source, InputSource.CLIPBOARD)
        self.assertEqual(clipboard_envelope.context.turn_type, InputType.CONTENT)
        self.assertNotIn("content", clipboard_envelope.to_dict())


class TestClapDetector(unittest.TestCase):
    def test_two_impulses_wake_without_stt(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]
        silence = [0.0] * 100

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertEqual(detector.pop_decision(), "FIRST_CLAP")
        self.assertFalse(detector.process(silence, 1.10))
        self.assertFalse(detector.process(impulse, 1.35))
        self.assertEqual(detector.pop_decision(), "DOUBLE_PENDING")
        self.assertFalse(detector.process(silence, 1.58))
        self.assertTrue(detector.process(silence, 1.86))
        self.assertEqual(detector.pop_decision(), "CONFIRMED")

    def test_single_clap_never_wakes(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]
        silence = [0.0] * 100

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertFalse(detector.process(silence, 2.0))

    def test_fast_third_clap_cancels_pending_double_clap(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]
        silence = [0.0] * 100

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertFalse(detector.process(silence, 1.10))
        self.assertFalse(detector.process(impulse, 1.3))
        self.assertFalse(detector.process(impulse, 1.45))
        self.assertEqual(detector.pop_decision(), "TRIPLE_CANCELLED")
        self.assertFalse(detector.process(silence, 1.8))

    def test_slow_third_clap_within_valid_gap_cancels_double_clap(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]
        silence = [0.0] * 100

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertFalse(detector.process(silence, 1.10))
        self.assertFalse(detector.process(impulse, 1.3))
        self.assertFalse(detector.process(silence, 1.75))
        self.assertFalse(detector.process(impulse, 1.9))
        self.assertFalse(detector.process(silence, 2.8))

    def test_sustained_loud_audio_is_not_a_clap(self):
        detector = ClapDetector()
        sustained = [0.7] * 100

        self.assertFalse(detector.process(sustained, 1.0))
        self.assertFalse(detector.process(sustained, 1.4))

    def test_late_second_clap_starts_a_new_pair(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]
        silence = [0.0] * 100

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertFalse(detector.process(silence, 1.10))
        self.assertFalse(detector.process(impulse, 2.0))
        self.assertFalse(detector.process(silence, 2.10))
        self.assertFalse(detector.process(impulse, 2.3))
        self.assertTrue(detector.process([0.0] * 100, 2.81))

    def test_detector_explains_gap_rejections(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]

        self.assertFalse(detector.process(impulse, 1.0))
        detector.pop_decision()
        detector.pop_diagnostic()
        self.assertFalse(detector.process([0.0] * 100, 1.10))
        detector.pop_diagnostic()
        self.assertFalse(detector.process(impulse, 1.9))

        diagnostic = detector.pop_diagnostic()
        self.assertEqual(diagnostic["detector_state"], "FIRST_CLAP")
        self.assertEqual(diagnostic["rejection_reason"], "gap_above_max")
        self.assertAlmostEqual(diagnostic["gap_seconds"], 0.9)

    def test_detector_explains_refractory_rejections(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]

        self.assertFalse(detector.process(impulse, 1.0))
        detector.pop_decision()
        detector.pop_diagnostic()
        self.assertFalse(detector.process(impulse, 1.05))

        diagnostic = detector.pop_diagnostic()
        self.assertEqual(diagnostic["detector_state"], "REJECTED")
        self.assertEqual(diagnostic["rejection_reason"], "refractory")
        self.assertAlmostEqual(diagnostic["gap_seconds"], 0.05)

    def test_pending_double_preserves_first_clap_until_settle_confirmation(self):
        detector = ClapDetector()
        impulse = [0.0] * 99 + [1.0]
        silence = [0.0] * 100

        self.assertFalse(detector.process(impulse, 1.0))
        self.assertFalse(detector.process(silence, 1.10))
        self.assertFalse(detector.process(impulse, 1.45))
        self.assertFalse(detector.process(silence, 1.85))
        self.assertTrue(detector.process(silence, 1.96))

        diagnostic = detector.pop_diagnostic()
        self.assertEqual(diagnostic["detector_state"], "CONFIRMED")
        self.assertAlmostEqual(diagnostic["gap_seconds"], 0.45)
        self.assertIsNone(detector.first_clap_at)
        self.assertIsNone(detector.second_clap_at)

    def test_second_clap_uses_adaptive_threshold_after_strict_first_clap(self):
        detector = ClapDetector()
        strict_first = [0.0] * 99 + [1.0]
        weaker_second = [0.0] * 97 + [0.4, 0.4, 0.4]

        self.assertFalse(detector.process(strict_first, 1.0))
        self.assertFalse(detector.process([0.0] * 100, 1.10))
        self.assertEqual(
            detector.pop_diagnostic()["detector_state"],
            "SECOND_CLAP_ARMED",
        )
        self.assertFalse(detector.process(weaker_second, 1.45))

        self.assertEqual(detector.pop_decision(), "DOUBLE_PENDING")
        self.assertAlmostEqual(detector.second_clap_at, 1.45)

    def test_first_clap_echo_cannot_arm_or_become_second_clap(self):
        detector = ClapDetector()
        strict_impulse = [0.0] * 99 + [1.0]

        self.assertFalse(detector.process(strict_impulse, 1.0))
        detector.pop_decision()
        detector.pop_diagnostic()
        self.assertFalse(detector.process(strict_impulse, 1.15))

        diagnostic = detector.pop_diagnostic()
        self.assertEqual(diagnostic["detector_state"], "REJECTED")
        self.assertEqual(diagnostic["rejection_reason"], "signal_not_released")
        self.assertFalse(diagnostic["signal_released"])
        self.assertIsNone(detector.second_clap_at)

    def test_weak_third_clap_uses_adaptive_guard_and_cancels_activation(self):
        detector = ClapDetector()
        strict_first = [0.0] * 99 + [1.0]
        weaker_clap = [0.0] * 97 + [0.4, 0.4, 0.4]
        silence = [0.0] * 100

        self.assertFalse(detector.process(strict_first, 1.0))
        self.assertFalse(detector.process(silence, 1.10))
        self.assertFalse(detector.process(weaker_clap, 1.30))
        detector.pop_decision()
        self.assertFalse(detector.process(weaker_clap, 1.55))

        self.assertEqual(detector.pop_decision(), "TRIPLE_CANCELLED")
        self.assertEqual(
            detector.pop_diagnostic()["rejection_reason"],
            "third_clap",
        )

    def test_missing_first_clap_is_rejected_without_callback_exception(self):
        detector = ClapDetector()
        detector.second_clap_at = 1.45

        self.assertFalse(detector.process([0.0] * 100, 1.96))

        diagnostic = detector.pop_diagnostic()
        self.assertEqual(diagnostic["detector_state"], "REJECTED")
        self.assertEqual(diagnostic["rejection_reason"], "missing_first_clap")
        self.assertIsNone(detector.first_clap_at)
        self.assertIsNone(detector.second_clap_at)

    def test_audio_monitor_isolates_listener_exceptions(self):
        received = []

        def failing_listener(samples, timestamp):
            del samples, timestamp
            raise TypeError("simulated callback failure")

        monitor = SoundDeviceClapMonitor(failing_listener)
        monitor.add_listener(lambda samples, timestamp: received.append((samples, timestamp)))

        monitor.dispatch_audio((0.1,), 1.0)

        self.assertEqual(received, [((0.1,), 1.0)])


class TestWakeProvidersAndManager(unittest.TestCase):
    def test_manager_pause_discards_pending_wake_and_resume_accepts_new_wake(self):
        voice = WakeWordProvider(("jarvis",))
        manager = WakeManager((voice,))
        voice.feed_text("jarvis")

        manager.pause("dashboard_turn")

        self.assertTrue(manager.is_paused())
        self.assertIsNone(voice.poll())
        manager.resume("browser_ack")
        voice.feed_text("jarvis")
        self.assertEqual(manager.wait(timeout=0.05).method, WakeMethod.VOICE)

    def test_stopped_transcriber_rejects_inflight_stt_result(self):
        started = Event()
        release = Event()
        recognized = []

        def transcribe(_audio):
            started.set()
            release.wait(timeout=1.0)
            return "jarvis"

        transcriber = WakePhraseTranscriber(transcribe, recognized.append)
        transcriber.start()
        transcriber.submit(b"wake-audio")
        self.assertTrue(started.wait(timeout=0.5))
        Timer(0.05, release.set).start()

        transcriber.stop()

        self.assertEqual(recognized, [])

    def test_profile_priority_selects_clap_before_voice(self):
        clap = ClapWakeProvider()
        voice = WakeWordProvider()
        clap.trigger()
        voice.feed_text("헤이 자비스")
        manager = WakeManager((voice, clap))

        event = manager.wait(timeout=0.01)

        self.assertEqual(event.method, WakeMethod.CLAP)

    def test_selected_wake_clears_simultaneous_provider_events(self):
        clap = ClapWakeProvider()
        voice = WakeWordProvider()
        clap.trigger()
        voice.feed_text("자비스")
        manager = WakeManager((voice, clap))

        self.assertEqual(manager.wait(timeout=0.01).method, WakeMethod.CLAP)
        self.assertIsNone(manager.wait(timeout=0.01))

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
        segmenter.process(speech, 1.10)
        segmenter.process(speech, 1.15)
        for index in range(12):
            segmenter.process(silence, 1.20 + index * 0.05)

        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0].startswith(b"RIFF"))

    def test_speech_segmenter_rejects_separated_clap_impulses(self):
        segments = []
        segmenter = SpeechSegmenter(segments.append)
        clap = [0.20] * 800
        silence = [0.0] * 800

        segmenter.process(clap, 1.00)
        segmenter.process(clap, 1.05)
        segmenter.process(silence, 1.10)
        segmenter.process(silence, 1.15)
        segmenter.process(clap, 1.25)
        segmenter.process(clap, 1.30)
        for index in range(12):
            segmenter.process(silence, 1.35 + index * 0.05)

        self.assertEqual(segments, [])

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
                    "clap_peak_threshold": 0.7,
                    "clap_settle_seconds": 0.3,
                    "clap_second_threshold_ratio": 0.6,
                    "clap_release_threshold_ratio": 0.3,
                    "clap_noise_floor_multiplier": 5.0,
                }
            }
        )

        self.assertEqual(config.wake.primary, "voice")
        self.assertEqual(config.wake.methods, ("voice", "keyboard"))
        self.assertEqual(config.wake.voice_phrases, ("jarvis", "자비스"))
        self.assertEqual(config.wake.keyboard_hotkey, "alt+j")
        self.assertEqual(config.wake.clap_peak_threshold, 0.7)
        self.assertEqual(config.wake.clap_settle_seconds, 0.3)
        self.assertEqual(config.wake.clap_second_threshold_ratio, 0.6)
        self.assertEqual(config.wake.clap_release_threshold_ratio, 0.3)
        self.assertEqual(config.wake.clap_noise_floor_multiplier, 5.0)

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
        self.provider.feed_audio([0.0] * 100, 1.1)
        self.provider.feed_audio(impulse, 1.3)
        self.provider.feed_audio([0.0] * 100, 1.85)
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
