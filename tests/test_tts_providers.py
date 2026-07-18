import io
import os
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis.config.loader import create_config_from_dict
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.voice.providers import (
    ConsoleSpeechToTextProvider,
    ConsoleTextToSpeechProvider,
    HybridSpeechToTextProvider,
    MicrophoneSpeechToTextProvider,
    OpenAISpeechToTextProvider,
    OpenAITextToSpeechProvider,
    PiperTextToSpeechProvider,
    Pyttsx3TextToSpeechProvider,
    create_stt_provider,
    create_tts_provider,
    extract_transcription_metadata,
    is_suspicious_tts_duration,
    record_until_silence,
    select_stt_fallback_text,
    transcribe_confirmation_audio,
    transcribe_stt_audio,
)
from jarvis.voice.profiles import VoiceRegistry
from jarvis.voice.stt import (
    TranscriptQualityGate,
    TranscriptResult,
    get_stt_metrics_snapshot,
    render_stt_metrics_console,
    reset_stt_metrics,
)
from jarvis.voice.playback import (
    CompositePlaybackBackend,
    PlaybackResult,
    PowerShellPlaybackBackend,
    WinsoundPlaybackBackend,
    create_default_playback_backend,
    inspect_wav_file,
    normalize_wav_for_windows,
)


class TestTTSProviders(unittest.TestCase):
    """Test that TTS providers keep the shared speech contract."""

    def setUp(self):
        """Keep TTS tests independent from local .env debug settings."""
        self.previous_keep_tts_audio = os.environ.get("JARVIS_KEEP_TTS_AUDIO")
        self.previous_playback_backend = os.environ.get("JARVIS_PLAYBACK_BACKEND")
        self.previous_stt_min = os.environ.get("JARVIS_STT_MIN_SECONDS")
        self.previous_stt_max = os.environ.get("JARVIS_STT_MAX_SECONDS")
        self.previous_stt_silence = os.environ.get("JARVIS_STT_SILENCE_TIMEOUT")
        self.previous_stt_provider = os.environ.get("JARVIS_STT_PROVIDER")
        self.previous_stt_openai_model = os.environ.get("JARVIS_STT_OPENAI_MODEL")
        self.previous_stt_openai_language = os.environ.get("JARVIS_STT_OPENAI_LANGUAGE")
        self.previous_stt_fallback_enabled = os.environ.get("JARVIS_STT_FALLBACK_ENABLED")
        os.environ["JARVIS_KEEP_TTS_AUDIO"] = "false"
        os.environ["JARVIS_PLAYBACK_BACKEND"] = "auto"
        os.environ.pop("JARVIS_STT_MIN_SECONDS", None)
        os.environ.pop("JARVIS_STT_MAX_SECONDS", None)
        os.environ.pop("JARVIS_STT_SILENCE_TIMEOUT", None)
        os.environ["JARVIS_STT_PROVIDER"] = ""
        os.environ["JARVIS_STT_OPENAI_MODEL"] = ""
        os.environ["JARVIS_STT_OPENAI_LANGUAGE"] = ""
        os.environ["JARVIS_STT_FALLBACK_ENABLED"] = ""

    def tearDown(self):
        """Restore local TTS debug settings."""
        restore_env("JARVIS_KEEP_TTS_AUDIO", self.previous_keep_tts_audio)
        restore_env("JARVIS_PLAYBACK_BACKEND", self.previous_playback_backend)
        restore_env("JARVIS_STT_MIN_SECONDS", self.previous_stt_min)
        restore_env("JARVIS_STT_MAX_SECONDS", self.previous_stt_max)
        restore_env("JARVIS_STT_SILENCE_TIMEOUT", self.previous_stt_silence)
        restore_env("JARVIS_STT_PROVIDER", self.previous_stt_provider)
        restore_env("JARVIS_STT_OPENAI_MODEL", self.previous_stt_openai_model)
        restore_env("JARVIS_STT_OPENAI_LANGUAGE", self.previous_stt_openai_language)
        restore_env("JARVIS_STT_FALLBACK_ENABLED", self.previous_stt_fallback_enabled)

    def test_default_config_selects_pyttsx3_provider(self):
        """Check that pyttsx3 is the default local TTS provider."""
        config = create_config_from_dict({})

        provider = create_tts_provider(config.tts)

        self.assertIsInstance(provider, Pyttsx3TextToSpeechProvider)

    def test_config_selects_piper_provider(self):
        """Check that config can select the Piper TTS provider."""
        config = create_config_from_dict(
            {
                "tts": {
                    "provider": "piper",
                    "voice": "default",
                    "streaming": True,
                    "piper_path": "piper",
                    "model_path": "missing.onnx",
                }
            }
        )
        diagnostics = DiagnosticsCollector()

        provider = create_tts_provider(config.tts, diagnostics_collector=diagnostics)

        self.assertIsInstance(provider, PiperTextToSpeechProvider)
        self.assertEqual(provider.voice, "default")
        self.assertTrue(provider.streaming_enabled)
        self.assert_event_logged(diagnostics, "voice.provider.selected")

    def test_voice_registry_returns_profile(self):
        """Check voice profiles are resolved by registry."""
        profile = VoiceRegistry().get_profile("jarvis")

        self.assertEqual(profile.id, "jarvis_default")
        self.assertEqual(profile.display_name, "Jarvis")
        self.assertEqual(profile.provider, "openai")
        self.assertEqual(profile.voice, "alloy")
        self.assertEqual(profile.name, "JARVIS-inspired original")
        self.assertEqual(profile.accent, "British-inspired")
        self.assertEqual(profile.speed, 0.95)
        self.assertEqual(profile.emotion, "calm, composed, witty")
        self.assertEqual(profile.style, "private butler / hotel concierge")

    def test_config_selects_openai_tts_provider_with_profile(self):
        """Check config can select OpenAI TTS through a voice profile."""
        config = create_config_from_dict(
            {
                "tts_provider": "openai",
                "voice_profile": "jarvis_default",
                "tts": {
                    "openai_model": "gpt-4o-mini-tts",
                    "response_format": "wav",
                },
            }
        )

        provider = create_tts_provider(config.tts)

        self.assertIsInstance(provider, OpenAITextToSpeechProvider)
        self.assertEqual(provider.profile.id, "jarvis_default")
        self.assertEqual(provider.profile.voice, "alloy")
        self.assertEqual(provider.model, "gpt-4o-mini-tts")

    def test_tts_speed_env_override_is_float(self):
        """Check JARVIS_TTS_SPEED overrides profile speed as a float."""
        previous = os.environ.get("JARVIS_TTS_SPEED")
        os.environ["JARVIS_TTS_SPEED"] = "1.12"
        config = create_config_from_dict(
            {
                "tts_provider": "openai",
                "voice_profile": "jarvis_default",
                "tts": {
                    "openai_model": "gpt-4o-mini-tts",
                    "response_format": "wav",
                },
            }
        )

        try:
            provider = create_tts_provider(config.tts)
        finally:
            restore_env("JARVIS_TTS_SPEED", previous)

        self.assertEqual(provider.profile.speed, 1.12)
        self.assertIsInstance(provider.profile.speed, float)

    def test_openai_tts_provider_generates_audio_with_mocked_client(self):
        """Check OpenAI TTS uses profile voice and writes audio."""
        profile = VoiceRegistry().get_profile("jarvis_default")
        client = FakeOpenAITTSClient()
        provider = OpenAITextToSpeechProvider(
            profile=profile,
            model="gpt-4o-mini-tts",
            response_format="wav",
            client_factory=lambda api_key: client,
            api_key_reader=lambda: "test-key",
            playback_backend=FakePlaybackBackend(),
        )

        audio_path = provider.generate_audio("hello")

        try:
            self.assertTrue(audio_path.endswith(".wav"))
            with open(audio_path, "rb") as file:
                self.assertEqual(file.read(), b"RIFFfake")
        finally:
            provider_file_cleanup(audio_path)

        request = client.audio.speech.request
        self.assertEqual(request["model"], "gpt-4o-mini-tts")
        self.assertEqual(request["voice"], "alloy")
        self.assertEqual(request["input"], "hello")
        self.assertEqual(request["response_format"], "wav")
        self.assertEqual(request["speed"], 0.95)

    def test_tts_duration_warning_detects_short_audio(self):
        """Check suspiciously short TTS files are flagged without failing playback."""
        self.assertTrue(is_suspicious_tts_duration("일정을 등록했습니다.", 0.3))
        self.assertFalse(is_suspicious_tts_duration("일정을 등록했습니다.", 1.2))
        self.assertFalse(is_suspicious_tts_duration("네", 0.2))

    def test_openai_tts_provider_calls_audio_playback(self):
        """Check OpenAI TTS plays the generated audio file."""
        profile = VoiceRegistry().get_profile("jarvis_default")
        client = FakeOpenAITTSClient()
        provider = OpenAITextToSpeechProvider(
            profile=profile,
            model="gpt-4o-mini-tts",
            response_format="wav",
            client_factory=lambda api_key: client,
            api_key_reader=lambda: "test-key",
            playback_backend=FakePlaybackBackend(),
        )

        provider.speak("hello")

        self.assertEqual(provider.playback_backend.played_count, 1)
        self.assertEqual(provider.playback_backend.paths[0].suffix, ".wav")

    def test_tts_playback_is_serialized_across_concurrent_calls(self):
        """Check voice and reminder TTS cannot overlap playback."""
        profile = VoiceRegistry().get_profile("jarvis_default")
        backend = BlockingPlaybackBackend()
        providers = [
            OpenAITextToSpeechProvider(
                profile=profile,
                model="gpt-4o-mini-tts",
                response_format="wav",
                client_factory=lambda api_key: FakeOpenAITTSClient(),
                api_key_reader=lambda: "test-key",
                playback_backend=backend,
            )
            for _ in range(2)
        ]
        threads = [threading.Thread(target=provider.speak, args=(f"hello {index}",)) for index, provider in enumerate(providers)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(backend.played_count, 2)
        self.assertEqual(backend.max_active, 1)

    def test_winsound_backend_uses_blocking_filename_playback(self):
        """Check winsound playback does not use SND_ASYNC."""
        calls = []
        original_module = sys.modules.get("winsound")

        def fake_play_sound(path, flags):
            calls.append((path, flags))

        sys.modules["winsound"] = SimpleNamespace(
            SND_FILENAME=1,
            SND_ASYNC=2,
            SND_NODEFAULT=4,
            PlaySound=fake_play_sound,
        )

        try:
            result = WinsoundPlaybackBackend().play("voice.wav")
        finally:
            if original_module is None:
                sys.modules.pop("winsound", None)
            else:
                sys.modules["winsound"] = original_module

        self.assertTrue(result.success)
        self.assertEqual(calls, [(str(Path("voice.wav").resolve()), 5)])

    def test_powershell_backend_uses_playsync(self):
        """Check PowerShell playback uses blocking SoundPlayer.PlaySync."""
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("jarvis.voice.playback.os.name", "nt"):
            with patch("jarvis.voice.playback.subprocess.run", return_value=completed) as run:
                result = PowerShellPlaybackBackend(executable="powershell").play("voice.wav")

        command = run.call_args.args[0]
        self.assertTrue(result.success)
        self.assertIn("PlaySync()", command[-1])
        self.assertIn(str(Path("voice.wav").resolve()).replace("'", "''"), command[-1])

    def test_composite_backend_records_failed_attempts(self):
        """Check all playback attempts are preserved for debug traces."""
        backend = CompositePlaybackBackend([FailingPlaybackBackend(), FakePlaybackBackend()])

        result = backend.play("voice.wav")

        self.assertTrue(result.success)
        self.assertEqual([attempt.backend for attempt in result.attempts], ["failing_playback", "fake_playback"])
        self.assertEqual(result.attempts[0].error, "no device")

    def test_playback_backend_env_can_prioritize_simpleaudio(self):
        """Check JARVIS_PLAYBACK_BACKEND can move simpleaudio to the front."""
        os.environ["JARVIS_PLAYBACK_BACKEND"] = "simpleaudio"

        backend = create_default_playback_backend()

        self.assertTrue(backend.name.startswith("simpleaudio+"))

    def test_wav_format_inspection_reports_audio_metadata(self):
        """Check WAV metadata is available for playback debugging."""
        path = Path("output") / "tts" / "test_format.wav"
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            write_test_wav(path)
            metadata = inspect_wav_file(path)
        finally:
            provider_file_cleanup(path)

        self.assertEqual(metadata["sample_rate"], 16000)
        self.assertEqual(metadata["channels"], 1)
        self.assertEqual(metadata["sample_width"], 2)
        self.assertEqual(metadata["frame_count"], 1600)
        self.assertEqual(metadata["duration_sec"], 0.1)

    def test_streaming_wav_placeholders_are_normalized(self):
        """Check OpenAI streaming WAV placeholders are rewritten for Windows playback."""
        path = Path("output") / "tts" / "test_streaming_placeholder.wav"
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            path.write_bytes(create_streaming_placeholder_wav())
            result = normalize_wav_for_windows(path)
            content = path.read_bytes()
            metadata = inspect_wav_file(path)
        finally:
            provider_file_cleanup(path)

        self.assertTrue(result["normalized"])
        self.assertNotEqual(content[4:8], b"\xff\xff\xff\xff")
        self.assertNotEqual(content[40:44], b"\xff\xff\xff\xff")
        self.assertEqual(metadata["frame_count"], 4)

    def test_keep_tts_audio_writes_to_project_output_dir(self):
        """Check kept TTS files are written outside the temp directory."""
        profile = VoiceRegistry().get_profile("jarvis_default")
        client = FakeOpenAITTSClient()
        provider = OpenAITextToSpeechProvider(
            profile=profile,
            model="gpt-4o-mini-tts",
            response_format="wav",
            client_factory=lambda api_key: client,
            api_key_reader=lambda: "test-key",
        )
        previous = os.environ.get("JARVIS_KEEP_TTS_AUDIO")
        os.environ["JARVIS_KEEP_TTS_AUDIO"] = "true"
        audio_path = None

        try:
            audio_path = provider.generate_audio("hello")
            self.assertIn(str(Path("output") / "tts"), audio_path)
            self.assertTrue(Path(audio_path).exists())
            self.assertEqual(Path(audio_path).stat().st_size, 8)
        finally:
            provider_file_cleanup(audio_path)
            restore_env("JARVIS_KEEP_TTS_AUDIO", previous)

    def test_console_provider_speak_stream_contract(self):
        """Check console TTS streaming chunks and diagnostics events."""
        diagnostics = DiagnosticsCollector()
        provider = ConsoleTextToSpeechProvider(diagnostics_collector=diagnostics)

        output = io.StringIO()
        with redirect_stdout(output):
            provider.speak_stream(["hello", "world"])

        self.assertIn("hello", output.getvalue())
        self.assertIn("world", output.getvalue())
        self.assert_event_logged(diagnostics, "voice.tts.started")
        self.assert_event_logged(diagnostics, "voice.tts.chunk.generated")
        self.assert_event_logged(diagnostics, "voice.tts.playback.started")
        self.assert_event_logged(diagnostics, "voice.tts.playback.completed")

    def test_piper_provider_falls_back_when_not_configured(self):
        """Check that Piper keeps the contract even without local binaries."""
        diagnostics = DiagnosticsCollector()
        provider = PiperTextToSpeechProvider(
            piper_path="missing-piper-executable",
            model_path="missing.onnx",
            diagnostics_collector=diagnostics,
        )

        output = io.StringIO()
        with redirect_stdout(output):
            provider.speak("hello")

        self.assertIn("Falling back to console output", output.getvalue())
        self.assert_event_logged(diagnostics, "voice.tts.error")

    def test_pyttsx3_provider_queues_all_chunks_before_playback(self):
        """Check pyttsx3 queues every line and runs playback once."""
        engine = FakePyttsx3Engine()
        original_module = sys.modules.get("pyttsx3")
        sys.modules["pyttsx3"] = SimpleNamespace(init=lambda: engine)

        try:
            Pyttsx3TextToSpeechProvider().speak_stream("첫 문장\n재료:\n스파게티")
        finally:
            if original_module is None:
                sys.modules.pop("pyttsx3", None)
            else:
                sys.modules["pyttsx3"] = original_module

        self.assertEqual(engine.spoken, ["첫 문장", "재료:", "스파게티"])
        self.assertEqual(engine.run_count, 1)

    def test_factory_keeps_existing_provider_names(self):
        """Check existing console and pyttsx3 provider names still resolve."""
        self.assertIsInstance(create_tts_provider("console"), ConsoleTextToSpeechProvider)
        self.assertIsInstance(create_tts_provider("pyttsx3"), Pyttsx3TextToSpeechProvider)

    def test_default_config_selects_openai_stt_provider(self):
        """Check OpenAI STT is the default voice input provider."""
        config = create_config_from_dict({})

        provider = create_stt_provider(config.stt)

        self.assertIsInstance(provider, OpenAISpeechToTextProvider)

    def test_config_selects_microphone_stt_provider(self):
        """Check config can select the microphone STT provider."""
        config = create_config_from_dict(
            {
                "stt": {
                    "provider": "microphone",
                    "language": "ko-KR",
                    "device": "default",
                    "max_record_seconds": 12,
                    "silence_timeout": 1.2,
                }
            }
        )

        provider = create_stt_provider(config.stt)

        self.assertIsInstance(provider, MicrophoneSpeechToTextProvider)
        self.assertEqual(provider.language, "ko-KR")
        self.assertEqual(provider.device, "default")
        self.assertEqual(provider.max_record_seconds, 12.0)
        self.assertEqual(provider.silence_timeout, 1.2)

    def test_microphone_stt_defaults_are_memory_friendly(self):
        """Check default silence recording settings allow longer memory phrases."""
        config = create_config_from_dict({"stt": {"provider": "microphone"}})

        provider = create_stt_provider(config.stt)

        self.assertEqual(provider.min_record_seconds, 4.0)
        self.assertEqual(provider.max_record_seconds, 20.0)
        self.assertEqual(provider.silence_timeout, 3.0)

    def test_stt_env_aliases_override_silence_recording_settings(self):
        """Check requested STT env names tune silence-based recording."""
        previous_max = os.environ.get("JARVIS_STT_MAX_SECONDS")
        previous_silence = os.environ.get("JARVIS_STT_SILENCE_TIMEOUT")
        os.environ["JARVIS_STT_MAX_SECONDS"] = "13"
        os.environ["JARVIS_STT_SILENCE_TIMEOUT"] = "1.7"

        try:
            config = create_config_from_dict({"stt": {"provider": "microphone"}})
            provider = create_stt_provider(config.stt)
        finally:
            restore_env("JARVIS_STT_MAX_SECONDS", previous_max)
            restore_env("JARVIS_STT_SILENCE_TIMEOUT", previous_silence)

        self.assertEqual(provider.max_record_seconds, 13.0)
        self.assertEqual(provider.silence_timeout, 1.7)

    def test_sounddevice_recording_stops_after_silence(self):
        """Check fallback STT records until post-speech silence."""
        np = __import__("numpy")
        chunks = [
            np.ones((10, 1), dtype=np.int16) * 1000,
            np.ones((10, 1), dtype=np.int16) * 1000,
            np.zeros((10, 1), dtype=np.int16),
            np.zeros((10, 1), dtype=np.int16),
        ]
        sd = FakeSoundDevice(chunks)

        recording = record_until_silence(
            sd=sd,
            np=np,
            sample_rate=10,
            min_record_seconds=0.2,
            max_record_seconds=4.0,
            silence_timeout=0.4,
            silence_threshold=500,
            chunk_seconds=1.0,
        )

        self.assertEqual(sd.record_calls, 3)
        self.assertEqual(recording.shape[0], 30)

    def test_sounddevice_recording_respects_minimum_seconds(self):
        """Check early silence cannot stop recording before min seconds."""
        np = __import__("numpy")
        chunks = [
            np.ones((10, 1), dtype=np.int16) * 1000,
            np.zeros((10, 1), dtype=np.int16),
            np.zeros((10, 1), dtype=np.int16),
            np.zeros((10, 1), dtype=np.int16),
        ]
        sd = FakeSoundDevice(chunks)

        recording, metadata = record_until_silence(
            sd=sd,
            np=np,
            sample_rate=10,
            min_record_seconds=3.0,
            max_record_seconds=4.0,
            silence_timeout=1.0,
            silence_threshold=500,
            chunk_seconds=1.0,
            return_metadata=True,
        )

        self.assertEqual(sd.record_calls, 3)
        self.assertEqual(recording.shape[0], 30)
        self.assertEqual(metadata["end_reason"], "silence_timeout")
        self.assertEqual(metadata["recorded_seconds"], 3.0)

    def test_sounddevice_recording_detects_quiet_speech(self):
        """Check VAD starts for speech below the old aggressive RMS threshold."""
        np = __import__("numpy")
        chunks = [
            np.zeros((10, 1), dtype=np.int16),
            np.ones((10, 1), dtype=np.int16) * 120,
            np.ones((10, 1), dtype=np.int16) * 120,
            np.zeros((10, 1), dtype=np.int16),
        ]
        sd = FakeSoundDevice(chunks)

        recording, metadata = record_until_silence(
            sd=sd,
            np=np,
            sample_rate=10,
            min_record_seconds=0.2,
            max_record_seconds=4.0,
            silence_timeout=1.0,
            chunk_seconds=1.0,
            return_metadata=True,
        )

        self.assertTrue(metadata["speech_started"])
        self.assertEqual(metadata["end_reason"], "silence_timeout")
        self.assertEqual(recording.shape[0], 40)
        self.assertGreaterEqual(metadata["max_rms"], 120)

    def test_sounddevice_recording_reports_no_speech_for_silence(self):
        """Check all-silence recording reports max_seconds and no speech."""
        np = __import__("numpy")
        sd = FakeSoundDevice([np.zeros((10, 1), dtype=np.int16) for _ in range(3)])

        recording, metadata = record_until_silence(
            sd=sd,
            np=np,
            sample_rate=10,
            min_record_seconds=1.0,
            max_record_seconds=3.0,
            silence_timeout=1.0,
            chunk_seconds=1.0,
            return_metadata=True,
        )

        self.assertFalse(metadata["speech_started"])
        self.assertEqual(metadata["end_reason"], "max_seconds")
        self.assertEqual(recording.shape[0], 30)

    def test_config_selects_openai_stt_provider(self):
        """Check OpenAI STT provider can be selected for microphone transcription."""
        config = create_config_from_dict(
            {
                "stt": {
                    "provider": "openai",
                    "language": "ko-KR",
                    "openai_model": "gpt-4o-transcribe",
                }
            }
        )

        provider = create_stt_provider(config.stt)

        self.assertIsInstance(provider, OpenAISpeechToTextProvider)
        self.assertEqual(provider.model, "gpt-4o-transcribe")
        self.assertEqual(provider.language, "ko")

    def test_config_selects_hybrid_stt_provider(self):
        """Check hybrid STT enables OpenAI fallback over microphone primary."""
        config = create_config_from_dict(
            {
                "stt": {
                    "provider": "hybrid",
                    "language": "ko-KR",
                    "openai_model": "fake-transcribe",
                }
            }
        )

        provider = create_stt_provider(config.stt)

        self.assertIsInstance(provider, HybridSpeechToTextProvider)
        self.assertTrue(provider.openai_fallback_enabled)
        self.assertEqual(provider.openai_model, "fake-transcribe")

    def test_hybrid_stt_keeps_hangul_primary_over_latin_fallback(self):
        """Check OpenAI fallback cannot overwrite a better Korean Google result."""
        selected = select_stt_fallback_text(
            primary_text="아야",
            fallback_text="Aja.",
            reason="short_or_confirmation",
            confirmation_mode=False,
        )

        self.assertEqual(selected, "아야")

    def test_hybrid_stt_uses_fallback_for_confirmation_mode(self):
        """Check confirmation mode can still prefer OpenAI fallback."""
        selected = select_stt_fallback_text(
            primary_text="어",
            fallback_text="응",
            reason="short_or_confirmation",
            confirmation_mode=True,
        )

        self.assertEqual(selected, "응")

    def test_openai_stt_transcribes_audio_bytes(self):
        """Check shared OpenAI STT helper transcribes one WAV payload."""
        reset_stt_metrics()
        fake_client = FakeOpenAISTTClient(text="\uc11c\uc6b8\uc5ed")

        text = transcribe_stt_audio(
            b"RIFFfake",
            model="fake-transcribe",
            language="ko-KR",
            client_factory=lambda api_key: fake_client,
            api_key_reader=lambda: "test-key",
        )

        self.assertEqual(text, "\uc11c\uc6b8\uc5ed")
        request = fake_client.audio.transcriptions.request
        self.assertEqual(request["model"], "fake-transcribe")
        self.assertEqual(request["language"], "ko")
        snapshot = get_stt_metrics_snapshot()
        self.assertEqual(snapshot.total_requests, 1)
        self.assertEqual(snapshot.success_count, 1)
        self.assertEqual(snapshot.provider_requests["openai"], 1)

    def test_openai_stt_prompt_includes_runtime_context(self):
        """Check STT prompt can include compact runtime context."""
        fake_client = FakeOpenAISTTClient(text="\uc751")

        transcribe_stt_audio(
            b"RIFFfake",
            model="fake-transcribe",
            language="ko",
            prompt_context="pending_action=todo.delete; pending_title=\uc6b0\uc720 \uc0ac\uae30",
            client_factory=lambda api_key: fake_client,
            api_key_reader=lambda: "test-key",
        )

        prompt = fake_client.audio.transcriptions.request["prompt"]
        self.assertIn("pending_action=todo.delete", prompt)
        self.assertIn("\uc6b0\uc720 \uc0ac\uae30", prompt)

    def test_openai_stt_collects_logprob_metadata_when_present(self):
        """Check optional transcription logprobs are converted to metadata."""
        metadata = extract_transcription_metadata(
            SimpleNamespace(logprobs=[{"token": "\uc751", "logprob": -0.2}, {"token": "?", "logprob": -1.4}])
        )

        self.assertLess(metadata["min_logprob"], -1.0)
        self.assertIn("?", metadata["low_confidence_tokens"])

    def test_stt_metrics_records_missing_openai_key(self):
        """Check OpenAI STT failures are captured as TranscriptResult metrics."""
        reset_stt_metrics()

        text = transcribe_stt_audio(
            b"RIFFfake",
            model="fake-transcribe",
            language="ko-KR",
            client_factory=lambda api_key: FakeOpenAISTTClient(text="\uc751"),
            api_key_reader=lambda: "",
        )

        self.assertEqual(text, "")
        snapshot = get_stt_metrics_snapshot()
        self.assertEqual(snapshot.total_requests, 1)
        self.assertEqual(snapshot.failure_count, 1)
        self.assertEqual(snapshot.provider_failure["openai"], 1)

    def test_transcript_quality_gate_flags_unknown_confirmation(self):
        """Check quality gate keeps short confirmation failures out of execution."""
        result = TranscriptResult(success=True, text="Gr\u00f6nn", provider="openai")

        issues = TranscriptQualityGate().evaluate(
            result,
            expected_answer_type="confirmation",
            confirmation_decision="unknown",
        )

        self.assertIn("confirmation_unknown", [issue.code for issue in issues])

    def test_stt_metrics_console_renders_summary(self):
        """Check STT metrics can be rendered as a readable console block."""
        reset_stt_metrics()
        transcribe_stt_audio(
            b"RIFFfake",
            model="fake-transcribe",
            language="ko",
            client_factory=lambda api_key: FakeOpenAISTTClient(text="\uc751"),
            api_key_reader=lambda: "test-key",
        )

        console = render_stt_metrics_console()

        self.assertIn("========== STT ==========", console)
        self.assertIn("Provider        : openai", console)
        self.assertIn("Requests        : 1", console)
        self.assertIn("Success         : 1", console)

    def test_confirmation_stt_can_fallback_to_openai_transcription(self):
        """Check confirmation clips can be transcribed by OpenAI fallback."""
        previous_provider = os.environ.get("JARVIS_CONFIRMATION_STT_PROVIDER")
        previous_model = os.environ.get("JARVIS_CONFIRMATION_STT_MODEL")
        os.environ["JARVIS_CONFIRMATION_STT_PROVIDER"] = "openai"
        os.environ["JARVIS_CONFIRMATION_STT_MODEL"] = "fake-transcribe"
        fake_client = FakeOpenAISTTClient(text="\uc751")

        try:
            text = transcribe_confirmation_audio(
                b"RIFFfake",
                client_factory=lambda api_key: fake_client,
                api_key_reader=lambda: "test-key",
            )
        finally:
            restore_env("JARVIS_CONFIRMATION_STT_PROVIDER", previous_provider)
            restore_env("JARVIS_CONFIRMATION_STT_MODEL", previous_model)

        self.assertEqual(text, "\uc751")
        self.assertEqual(fake_client.audio.transcriptions.request["model"], "fake-transcribe")
        self.assertEqual(fake_client.audio.transcriptions.request["language"], "ko")

    def test_confirmation_stt_fallback_can_be_disabled(self):
        """Check confirmation OpenAI fallback can be disabled by config."""
        previous_provider = os.environ.get("JARVIS_CONFIRMATION_STT_PROVIDER")
        os.environ["JARVIS_CONFIRMATION_STT_PROVIDER"] = "none"

        try:
            text = transcribe_confirmation_audio(
                b"RIFFfake",
                client_factory=lambda api_key: FakeOpenAISTTClient(text="\uc751"),
                api_key_reader=lambda: "test-key",
            )
        finally:
            restore_env("JARVIS_CONFIRMATION_STT_PROVIDER", previous_provider)

        self.assertEqual(text, "")

    def assert_event_logged(self, diagnostics, expected_message):
        """Check that one diagnostics event was logged."""
        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn(expected_message, messages)


class FakePyttsx3Engine:
    """Minimal pyttsx3 engine fake."""

    def __init__(self):
        """Create fake engine state."""
        self.spoken = []
        self.run_count = 0

    def say(self, text):
        """Capture queued speech."""
        self.spoken.append(text)

    def runAndWait(self):
        """Capture playback start."""
        self.run_count += 1

    def stop(self):
        """Keep the engine API shape."""
        return None


class FakeOpenAITTSClient:
    """Minimal fake OpenAI TTS client."""

    def __init__(self):
        """Create fake audio resources."""
        self.audio = SimpleNamespace(speech=FakeOpenAITTSSpeech())


class FakeOpenAITTSSpeech:
    """Fake speech resource."""

    def __init__(self):
        """Create fake speech state."""
        self.request = {}

    def create(self, **request):
        """Capture request and return fake audio content."""
        self.request = request
        return SimpleNamespace(content=b"RIFFfake")


class FakeOpenAISTTClient:
    """Minimal fake OpenAI STT client."""

    def __init__(self, text, logprobs=None):
        """Create fake transcription resources."""
        self.audio = SimpleNamespace(transcriptions=FakeOpenAITranscriptions(text=text, logprobs=logprobs))


class FakeOpenAITranscriptions:
    """Fake transcriptions resource."""

    def __init__(self, text, logprobs=None):
        """Create fake transcription state."""
        self.text = text
        self.logprobs = logprobs
        self.request = {}

    def create(self, **request):
        """Capture request and return fake transcription text."""
        self.request = request
        return SimpleNamespace(text=self.text, logprobs=self.logprobs)


class FakePlaybackBackend:
    """Fake blocking playback backend for OpenAI TTS tests."""

    name = "fake_playback"

    def __init__(self):
        """Create fake playback state."""
        self.paths = []
        self.played_count = 0

    def play(self, path):
        """Capture playback and report a completed blocking result."""
        self.played_count += 1
        self.paths.append(Path(path))
        file_size = Path(path).stat().st_size if Path(path).exists() else 0
        return PlaybackResult(True, self.name, str(path), file_size, blocking=True)


class BlockingPlaybackBackend:
    """Fake slow playback backend that detects overlap."""

    name = "blocking_playback"

    def __init__(self):
        """Create playback counters."""
        self.paths = []
        self.played_count = 0
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def play(self, path):
        """Sleep briefly while recording concurrent playback."""
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.played_count += 1
            self.paths.append(Path(path))

        time.sleep(0.05)

        with self.lock:
            self.active -= 1

        file_size = Path(path).stat().st_size if Path(path).exists() else 0
        return PlaybackResult(True, self.name, str(path), file_size, blocking=True)


class FakeSoundDevice:
    """Fake sounddevice module for silence-based STT tests."""

    def __init__(self, chunks):
        """Create fake audio chunks."""
        self.chunks = list(chunks)
        self.record_calls = 0

    def rec(self, frames, samplerate, channels, dtype, device=None):
        """Return the next fake chunk."""
        self.record_calls += 1

        if len(self.chunks) == 0:
            np = __import__("numpy")
            return np.zeros((frames, channels), dtype=dtype)

        return self.chunks.pop(0)

    def wait(self):
        """Match sounddevice wait API."""
        return None


class FailingPlaybackBackend:
    """Fake failed playback backend for attempt logging tests."""

    name = "failing_playback"

    def play(self, path):
        """Return a failed playback result."""
        return PlaybackResult(False, self.name, str(path), 0, "no device", blocking=True)


def write_test_wav(path):
    """Write a tiny valid PCM WAV file."""
    import wave

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\0\0" * 1600)


def create_streaming_placeholder_wav():
    """Create a tiny PCM WAV with streaming placeholder chunk sizes."""
    fmt_data = (
        (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (24000).to_bytes(4, "little")
        + (48000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
    )
    data = b"\0\0" * 4
    return (
        b"RIFF"
        + b"\xff\xff\xff\xff"
        + b"WAVE"
        + b"fmt "
        + len(fmt_data).to_bytes(4, "little")
        + fmt_data
        + b"data"
        + b"\xff\xff\xff\xff"
        + data
    )


def provider_file_cleanup(path):
    """Remove a generated test file."""
    import os

    try:
        os.remove(path)
    except OSError:
        return


def restore_env(key, previous):
    """Restore an environment variable after a test."""
    if previous is None:
        os.environ.pop(key, None)
        return

    os.environ[key] = previous


if __name__ == "__main__":
    unittest.main()
