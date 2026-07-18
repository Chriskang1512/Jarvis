import os
import math
import subprocess
import tempfile
import threading
import wave
from collections.abc import Iterable
from datetime import datetime
from io import BytesIO
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from typing import Protocol

from jarvis.voice.models import VoiceResult
from jarvis.voice.provider import VoiceProvider
from jarvis.voice.profiles import VoiceRegistry, apply_voice_overrides
from jarvis.voice.providers.mock import MockVoiceProvider
from jarvis.voice.providers.openai import OpenAIVoiceProvider
from jarvis.voice.stt import TranscriptResult, record_stt_result
from jarvis.voice.playback import (
    create_default_playback_backend,
    find_executable,
    get_file_size,
    inspect_wav_file,
    normalize_wav_for_windows,
    play_wav_file,
)
from jarvis.debug_trace import read_env_file_value, trace_event


_TTS_PLAYBACK_LOCK = threading.RLock()


def serialize_tts_call(function):
    """Serialize all local TTS generation/playback in one process."""
    def wrapped(*args, **kwargs):
        with _TTS_PLAYBACK_LOCK:
            return function(*args, **kwargs)

    return wrapped


class SpeechToTextProvider(Protocol):
    """Interface for speech-to-text providers."""

    def listen(self):
        """Listen for speech and return transcribed text."""
        ...


class TextToSpeechProvider(Protocol):
    """Interface for text-to-speech providers."""

    def speak(self, text):
        """Speak one text response."""
        ...

    def speak_stream(self, text, session=None):
        """Speak one text response in stream-ready chunks."""
        ...


class ConsoleSpeechToTextProvider:
    """Keyboard fallback provider for testing the voice pipeline."""

    def listen(self):
        """Read user text from the console instead of a microphone."""
        return input("Voice input > ").strip()


class OpenAISpeechToTextProvider:
    """OpenAI-backed speech-to-text provider using the shared microphone recorder."""

    def __init__(
        self,
        model="gpt-4o-transcribe",
        language="ko-KR",
        device="default",
        sample_rate=16000,
        min_record_seconds=4.0,
        max_record_seconds=20.0,
        silence_timeout=3.0,
        silence_threshold=80,
        client_factory=None,
        api_key_reader=None,
    ):
        """Create an OpenAI STT provider."""
        self.model = model
        self.language = language
        self.device = device
        self.sample_rate = sample_rate
        self.min_record_seconds = float(min_record_seconds)
        self.max_record_seconds = float(max_record_seconds)
        self.silence_timeout = float(silence_timeout)
        self.silence_threshold = int(silence_threshold)
        self.client_factory = client_factory
        self.api_key_reader = api_key_reader or read_openai_tts_api_key
        self.prompt_context = ""

    def listen(self):
        """Listen through the microphone and transcribe with OpenAI."""
        return self.listen_with_openai()

    def set_prompt_context(self, prompt_context):
        """Set short runtime context for the next transcription request."""
        self.prompt_context = str(prompt_context or "")

    def listen_for_confirmation(self, timeout=None):
        """Listen with shorter timing for yes/no confirmation."""
        return self.listen_with_temporary_timing(
            min_record_seconds=1.0,
            max_record_seconds=min(float(timeout or 5.0), 5.0),
            silence_timeout=1.2,
        )

    def listen_with_temporary_timing(self, min_record_seconds, max_record_seconds, silence_timeout):
        """Temporarily override silence recording timing."""
        original = (self.min_record_seconds, self.max_record_seconds, self.silence_timeout)
        self.min_record_seconds = float(min_record_seconds)
        self.max_record_seconds = float(max_record_seconds)
        self.silence_timeout = float(silence_timeout)

        try:
            return self.listen()
        finally:
            self.min_record_seconds, self.max_record_seconds, self.silence_timeout = original

    def listen_with_openai(self):
        """Record local audio and send it to OpenAI transcription."""
        audio_data = record_microphone_wav_bytes(
            sample_rate=self.sample_rate,
            device=self.device,
            min_record_seconds=self.min_record_seconds,
            max_record_seconds=self.max_record_seconds,
            silence_timeout=self.silence_timeout,
            silence_threshold=self.silence_threshold,
        )

        if isinstance(audio_data, str):
            return audio_data

        return transcribe_stt_audio(
            audio_data,
            model=self.model,
            language=self.language,
            provider="openai",
            reason="primary",
            prompt_context=self.prompt_context,
            client_factory=self.client_factory,
            api_key_reader=self.api_key_reader,
        )

class MicrophoneSpeechToTextProvider:
    """Microphone STT provider using the SpeechRecognition package."""

    def __init__(
        self,
        language="ko-KR",
        device="default",
        duration_seconds=5,
        sample_rate=16000,
        min_record_seconds=4.0,
        max_record_seconds=20.0,
        silence_timeout=3.0,
        silence_threshold=80,
        openai_fallback_enabled=False,
        openai_model="gpt-4o-transcribe",
        openai_language="ko",
        client_factory=None,
        api_key_reader=None,
    ):
        """Create a microphone STT provider."""
        self.language = language
        self.device = device
        self.duration_seconds = duration_seconds
        self.sample_rate = sample_rate
        self.min_record_seconds = float(min_record_seconds)
        self.max_record_seconds = float(max_record_seconds or duration_seconds)
        self.silence_timeout = float(silence_timeout)
        self.silence_threshold = int(silence_threshold)
        self.confirmation_mode = False
        self.openai_fallback_enabled = bool(openai_fallback_enabled)
        self.openai_model = openai_model
        self.openai_language = openai_language
        self.client_factory = client_factory
        self.api_key_reader = api_key_reader or read_openai_tts_api_key
        self.prompt_context = ""

    def listen(self):
        """Listen through the microphone and return recognized text."""
        try:
            import speech_recognition as sr
        except ImportError:
            return "SpeechRecognition package is not installed."

        return self.listen_with_speech_recognition(sr)

    def set_prompt_context(self, prompt_context):
        """Set short runtime context for OpenAI fallback transcription."""
        self.prompt_context = str(prompt_context or "")

    def listen_for_confirmation(self, timeout=None):
        """Listen with shorter timing for yes/no confirmation."""
        return self.listen_with_temporary_timing(
            min_record_seconds=1.0,
            max_record_seconds=min(float(timeout or 5.0), 5.0),
            silence_timeout=1.2,
            confirmation_mode=True,
        )

    def listen_with_temporary_timing(self, min_record_seconds, max_record_seconds, silence_timeout, confirmation_mode=False):
        """Temporarily override silence recording timing."""
        original = (self.min_record_seconds, self.max_record_seconds, self.silence_timeout, self.confirmation_mode)
        self.min_record_seconds = float(min_record_seconds)
        self.max_record_seconds = float(max_record_seconds)
        self.silence_timeout = float(silence_timeout)
        self.confirmation_mode = bool(confirmation_mode)

        try:
            return self.listen()
        finally:
            self.min_record_seconds, self.max_record_seconds, self.silence_timeout, self.confirmation_mode = original

    def listen_with_speech_recognition(self, sr):
        """Use SpeechRecognition microphone when PyAudio is available."""
        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                print("Listening...")
                audio = recognizer.listen(source)
        except Exception as error:
            return self.listen_with_sounddevice(sr, recognizer, error)

        try:
            google_text = recognizer.recognize_google(audio, language=self.language)
            trace_event(
                "voice.stt.provider_result",
                provider="google",
                success=True,
                text=google_text,
            )
            if self.should_verify_with_openai(google_text):
                fallback_text = self.transcribe_with_openai_fallback(audio.get_wav_data(), google_text, "short_or_confirmation")

                if fallback_text != "":
                    return select_stt_fallback_text(
                        primary_text=google_text,
                        fallback_text=fallback_text,
                        reason="short_or_confirmation",
                        confirmation_mode=self.confirmation_mode,
                    )

            return google_text
        except Exception as error:
            trace_event(
                "voice.stt.provider_result",
                provider="google",
                success=False,
                error=str(error),
            )
            if self.should_fallback_to_openai():
                fallback_text = self.transcribe_with_openai_fallback(audio.get_wav_data(), "", "primary_failed")

                if fallback_text != "":
                    return select_stt_fallback_text(
                        primary_text="",
                        fallback_text=fallback_text,
                        reason="primary_failed",
                        confirmation_mode=self.confirmation_mode,
                    )

            return f"Speech recognition failed: {error}"

    def listen_with_sounddevice(self, sr, recognizer, microphone_error):
        """Use sounddevice recording when PyAudio-backed microphone is unavailable."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError:
            return f"Microphone input failed: {microphone_error}"

        try:
            print(
                "Listening until silence "
                f"(min {self.min_record_seconds:g}s, max {self.max_record_seconds:g}s, "
                f"silence {self.silence_timeout:g}s)..."
            )
            device = None if self.device == "default" else self.device
            recording, recording_metadata = record_sounddevice_audio(
                sd=sd,
                np=np,
                sample_rate=self.sample_rate,
                device=device,
                min_record_seconds=self.min_record_seconds,
                max_record_seconds=self.max_record_seconds,
                silence_timeout=self.silence_timeout,
                silence_threshold=self.silence_threshold,
            )
            audio_data = create_wav_bytes(recording, self.sample_rate, np)
        except Exception as error:
            return f"Microphone input failed: {error}"

        try:
            with sr.AudioFile(BytesIO(audio_data)) as source:
                audio = recognizer.record(source)
            google_text = recognizer.recognize_google(audio, language=self.language)
            trace_event(
                "voice.stt.provider_result",
                provider="google",
                success=True,
                text=google_text,
            )
            if self.should_verify_with_openai(google_text):
                fallback_text = self.transcribe_with_openai_fallback(audio_data, google_text, "short_or_confirmation")

                if fallback_text != "":
                    return select_stt_fallback_text(
                        primary_text=google_text,
                        fallback_text=fallback_text,
                        reason="short_or_confirmation",
                        confirmation_mode=self.confirmation_mode,
                    )

            return google_text
        except Exception as error:
            trace_event(
                "voice.stt.provider_result",
                provider="google",
                success=False,
                error=str(error),
            )
            if self.should_fallback_to_openai():
                fallback_text = self.transcribe_with_openai_fallback(audio_data, "", "primary_failed")

                if fallback_text != "":
                    return select_stt_fallback_text(
                        primary_text="",
                        fallback_text=fallback_text,
                        reason="primary_failed",
                        confirmation_mode=self.confirmation_mode,
                    )

            return f"Speech recognition failed: {error}"

    def should_fallback_to_openai(self):
        """Return whether this turn may use OpenAI STT fallback."""
        return self.confirmation_mode or self.openai_fallback_enabled

    def should_verify_with_openai(self, google_text):
        """Return whether a Google transcript is risky enough to verify."""
        if not self.should_fallback_to_openai():
            return False

        if self.confirmation_mode:
            return True

        return is_short_stt_text(google_text)

    def transcribe_with_openai_fallback(self, audio_data, primary_text, reason):
        """Transcribe the same audio with OpenAI and prefer it when available."""
        text = transcribe_stt_audio(
            audio_data,
            model=self.openai_model,
            language=self.openai_language,
            provider="openai_fallback",
            reason=reason,
            prompt_context=self.prompt_context,
            client_factory=self.client_factory,
            api_key_reader=self.api_key_reader,
        )

        if text == "":
            return ""

        trace_event(
            "voice.stt.fallback",
            primary_provider="google",
            fallback_provider="openai",
            reason=reason,
            primary_text=primary_text,
            fallback_text=text,
            used=True,
        )
        return text


def select_stt_fallback_text(primary_text, fallback_text, reason, confirmation_mode=False):
    """Choose between primary and fallback STT without overwriting good Korean text."""
    primary = str(primary_text or "").strip()
    fallback = str(fallback_text or "").strip()

    if fallback == "":
        selected = primary
        source = "primary"
    elif primary == "":
        selected = fallback
        source = "fallback"
    elif confirmation_mode:
        selected = fallback
        source = "fallback"
    elif contains_hangul(primary) and not contains_hangul(fallback):
        selected = primary
        source = "primary"
    else:
        selected = fallback
        source = "fallback"

    trace_event(
        "voice.stt.fallback_selection",
        reason=reason,
        confirmation_mode=confirmation_mode,
        primary_text=primary,
        fallback_text=fallback,
        selected_source=source,
        selected_text=selected,
    )
    return selected


def contains_hangul(text):
    """Return whether text contains a Hangul syllable or jamo."""
    return any(
        "\uac00" <= char <= "\ud7a3"
        or "\u3130" <= char <= "\u318f"
        or "\u1100" <= char <= "\u11ff"
        for char in str(text or "")
    )


class HybridSpeechToTextProvider(MicrophoneSpeechToTextProvider):
    """Google microphone STT with OpenAI fallback for risky transcripts."""

    def __init__(self, *args, **kwargs):
        """Create a hybrid STT provider."""
        kwargs["openai_fallback_enabled"] = True
        super().__init__(*args, **kwargs)


class DiagnosticsMixin:
    """Publish voice diagnostics events when a collector is available."""

    def __init__(self, diagnostics_collector=None):
        """Create a diagnostics-aware provider."""
        self.diagnostics_collector = diagnostics_collector

    def log_event(self, message):
        """Publish one diagnostics event."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


class ConsoleTextToSpeechProvider(DiagnosticsMixin):
    """Console fallback provider for testing text-to-speech output."""

    def __init__(self, streaming=True, diagnostics_collector=None):
        """Create a console TTS provider."""
        super().__init__(diagnostics_collector=diagnostics_collector)
        self.streaming_enabled = streaming

    def speak(self, text):
        """Print speech text to the console."""
        with _TTS_PLAYBACK_LOCK:
            self.log_event("voice.tts.started")
            self.log_event("voice.tts.playback.started")
            print(f"Jarvis says: {text}")
            self.log_event("voice.tts.playback.completed")

    @serialize_tts_call
    def speak_stream(self, text, session=None):
        """Print speech chunks to the console."""
        self.log_event("voice.tts.started")
        self.log_event("voice.tts.playback.started")
        print("Jarvis says:")

        for chunk in normalize_speech_chunks(text):
            if should_stop_speaking(session):
                print("[voice interrupted]")
                self.log_event("voice.tts.playback.completed")
                return

            self.log_event("voice.tts.chunk.generated")
            print(chunk)

        self.log_event("voice.tts.playback.completed")


class Pyttsx3TextToSpeechProvider(DiagnosticsMixin):
    """Local TTS provider using pyttsx3."""

    def __init__(self, streaming=True, diagnostics_collector=None):
        """Create a pyttsx3 TTS provider."""
        super().__init__(diagnostics_collector=diagnostics_collector)
        self.streaming_enabled = streaming

    def speak(self, text):
        """Speak text using the local pyttsx3 engine."""
        self.speak_stream(text)

    @serialize_tts_call
    def speak_stream(self, text, session=None):
        """Speak text in chunks using the local pyttsx3 engine."""
        self.log_event("voice.tts.started")
        try:
            import pyttsx3
        except ImportError:
            self.log_event("voice.tts.error")
            print("pyttsx3 package is not installed.")
            print(f"Jarvis says: {text}")
            return

        engine = pyttsx3.init()
        self.log_event("voice.tts.playback.started")

        for chunk in normalize_speech_chunks(text):
            if should_stop_speaking(session):
                engine.stop()
                self.log_event("voice.tts.playback.completed")
                return

            self.log_event("voice.tts.chunk.generated")
            engine.say(chunk)

        engine.runAndWait()

        self.log_event("voice.tts.playback.completed")


class OpenAITextToSpeechProvider(DiagnosticsMixin):
    """OpenAI-backed TTS provider using a selected voice profile."""

    def __init__(
        self,
        profile,
        model="gpt-4o-mini-tts",
        response_format="wav",
        client_factory=None,
        api_key_reader=None,
        diagnostics_collector=None,
        playback_backend=None,
    ):
        """Create an OpenAI TTS provider."""
        super().__init__(diagnostics_collector=diagnostics_collector)
        self.profile = profile
        self.model = model
        self.response_format = response_format
        self.client_factory = client_factory
        self.api_key_reader = api_key_reader or read_openai_tts_api_key
        self.streaming_enabled = False
        self.playback_backend = playback_backend or create_default_playback_backend()

    def speak(self, text):
        """Generate speech audio and play it locally."""
        self.speak_stream(text)

    @serialize_tts_call
    def speak_stream(self, text, session=None):
        """Generate one non-streaming audio file and play it."""
        self.log_event("voice.tts.started")

        if should_stop_speaking(session):
            self.log_event("voice.tts.playback.completed")
            return

        audio_path = None
        try:
            audio_path = self.generate_audio(text)
            self.log_event("voice.tts.playback.started")
            trace_event(
                "voice.tts.playback.started",
                audio_file_path=audio_path,
                audio_file_size=get_file_size(audio_path),
                playback_backend=getattr(self.playback_backend, "name", "unknown"),
            )
            playback_result = self.playback_backend.play(audio_path)
            for attempt in playback_result.attempts:
                trace_event(
                    "voice.tts.playback.attempt",
                    playback_backend=attempt.backend,
                    playback_success=attempt.success,
                    playback_error=attempt.error,
                )

            trace_event(
                "voice.tts.playback.finished",
                audio_file_path=playback_result.path,
                audio_file_size=playback_result.file_size,
                playback_backend=playback_result.backend,
                playback_success=playback_result.success,
                playback_error=playback_result.error,
                playback_blocking=playback_result.blocking,
            )

            if not playback_result.success:
                raise RuntimeError(f"Audio playback failed ({playback_result.backend}): {playback_result.error}")

            self.log_event("voice.tts.playback.completed")
        except RuntimeError as error:
            self.log_event("voice.tts.error")
            trace_event(
                "voice.tts.playback.failed",
                audio_file_path=audio_path,
                audio_file_size=get_file_size(audio_path),
                playback_backend="unknown",
                playback_success=False,
                playback_error=str(error),
                playback_blocking=True,
            )
            print(error)
        finally:
            if should_keep_tts_audio():
                print(f"TTS audio saved: {audio_path}")
            else:
                remove_file_if_exists(audio_path)

    def generate_audio(self, text):
        """Generate a local audio file through OpenAI TTS."""
        api_key = self.api_key_reader()

        if api_key == "":
            raise RuntimeError("OpenAI TTS selected, but OPENAI_API_KEY was not found.")

        client = self.create_client(api_key)
        trace_event(
            "voice.tts.request.started",
            model=self.model,
            response_format=self.response_format,
            voice=self.profile.voice,
        )
        response = client.audio.speech.create(
            model=self.model,
            voice=self.profile.voice,
            input=str(text),
            response_format=self.response_format,
            speed=self.profile.speed,
        )
        audio_path = create_temp_audio_path(self.response_format)
        write_speech_response(response, audio_path)
        normalize_result = normalize_wav_for_windows(audio_path)
        wav_metadata = inspect_wav_file(audio_path)
        trace_event(
            "voice.tts.audio.normalized",
            audio_file_path=audio_path,
            normalized=normalize_result["normalized"],
            reason=normalize_result["reason"],
        )
        trace_event(
            "voice.tts.request.finished",
            tts_api_success=True,
            audio_file_path=audio_path,
            audio_file_size=get_file_size(audio_path),
            model=self.model,
            response_format=self.response_format,
        )
        trace_event(
            "voice.tts.audio.format",
            audio_file_path=audio_path,
            sample_rate=wav_metadata["sample_rate"],
            channels=wav_metadata["channels"],
            sample_width=wav_metadata["sample_width"],
            frame_count=wav_metadata["frame_count"],
            duration_sec=wav_metadata["duration_sec"],
            format_error=wav_metadata["format_error"],
        )
        if is_suspicious_tts_duration(text, wav_metadata["duration_sec"], wav_metadata["format_error"]):
            trace_event(
                "voice.tts.audio.warning",
                audio_file_path=audio_path,
                text_length=len(str(text)),
                duration_sec=wav_metadata["duration_sec"],
                reason="duration shorter than expected for text length",
            )
        return audio_path

    def create_client(self, api_key):
        """Create an OpenAI client or a test-injected client."""
        if self.client_factory is not None:
            return self.client_factory(api_key)

        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package is not installed. Run pip install -r requirements.txt.")

        return OpenAI(api_key=api_key)


class PiperTextToSpeechProvider(DiagnosticsMixin):
    """Local TTS provider using the Piper command-line runtime."""

    def __init__(
        self,
        voice="default",
        piper_path="piper",
        model_path="",
        streaming=True,
        diagnostics_collector=None,
    ):
        """Create a Piper TTS provider with configurable executable and model."""
        super().__init__(diagnostics_collector=diagnostics_collector)
        self.voice = voice
        self.piper_path = piper_path
        self.model_path = model_path
        self.streaming_enabled = streaming

    def speak(self, text):
        """Speak text through Piper."""
        self.speak_stream(text)

    @serialize_tts_call
    def speak_stream(self, text, session=None):
        """Generate Piper audio per chunk and play each generated WAV file."""
        self.log_event("voice.tts.started")

        if not self.is_available():
            self.log_event("voice.tts.error")
            print("Piper TTS is not configured. Falling back to console output.")
            ConsoleTextToSpeechProvider(diagnostics_collector=self.diagnostics_collector).speak_stream(
                text,
                session=session,
            )
            return

        self.log_event("voice.tts.playback.started")

        for chunk in normalize_speech_chunks(text):
            if should_stop_speaking(session):
                self.log_event("voice.tts.playback.completed")
                return

            self.log_event("voice.tts.chunk.generated")
            audio_path = None
            try:
                audio_path = self.generate_audio(chunk)
                play_wav_file(audio_path)
            except RuntimeError as error:
                self.log_event("voice.tts.error")
                print(error)
                return
            finally:
                remove_file_if_exists(audio_path)

        self.log_event("voice.tts.playback.completed")

    def is_available(self):
        """Return whether Piper executable and model are ready."""
        return find_executable(self.piper_path) is not None and Path(self.model_path).exists()

    def generate_audio(self, text):
        """Generate one WAV file through the Piper CLI."""
        output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_file.close()

        command = [
            self.piper_path,
            "--model",
            self.model_path,
            "--output_file",
            output_file.name,
        ]
        completed = subprocess.run(
            command,
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )

        if completed.returncode != 0:
            self.log_event("voice.tts.error")
            raise RuntimeError(f"Piper TTS failed: {completed.stderr.strip()}")

        return output_file.name


def create_stt_provider(provider_config):
    """Create a speech-to-text provider by name or config."""
    provider_name = read_stt_provider_name(provider_config)
    stt_kwargs = {
        "language": read_stt_config_value(provider_config, "language", "ko-KR"),
        "device": read_stt_config_value(provider_config, "device", "default"),
        "min_record_seconds": read_stt_float_config_value(provider_config, "min_record_seconds", 4.0),
        "max_record_seconds": read_stt_float_config_value(provider_config, "max_record_seconds", 20.0),
        "silence_timeout": read_stt_float_config_value(provider_config, "silence_timeout", 3.0),
    }

    if provider_name == "microphone":
        return MicrophoneSpeechToTextProvider(
            **stt_kwargs,
            openai_fallback_enabled=read_stt_bool_config_value(provider_config, "fallback_enabled", False),
            openai_model=read_stt_config_value(provider_config, "openai_model", "gpt-4o-transcribe"),
            openai_language=read_stt_config_value(provider_config, "openai_language", "ko"),
        )

    if provider_name == "openai":
        openai_stt_kwargs = dict(stt_kwargs)
        openai_stt_kwargs["language"] = read_stt_config_value(provider_config, "openai_language", "ko")
        return OpenAISpeechToTextProvider(
            **openai_stt_kwargs,
            model=read_stt_config_value(provider_config, "openai_model", "gpt-4o-transcribe"),
        )

    if provider_name == "hybrid":
        return HybridSpeechToTextProvider(
            **stt_kwargs,
            openai_model=read_stt_config_value(provider_config, "openai_model", "gpt-4o-transcribe"),
            openai_language=read_stt_config_value(provider_config, "openai_language", "ko"),
        )

    return ConsoleSpeechToTextProvider()


def create_tts_provider(provider_config, diagnostics_collector=None):
    """Create a text-to-speech provider by name."""
    profile = resolve_voice_profile(provider_config)
    provider_name = read_provider_name(provider_config, profile=profile)

    log_provider_selected(diagnostics_collector, provider_name)

    if provider_name == "openai":
        return OpenAITextToSpeechProvider(
            profile=profile,
            model=read_config_value(provider_config, "openai_model", "gpt-4o-mini-tts"),
            response_format=read_config_value(provider_config, "response_format", "wav"),
            diagnostics_collector=diagnostics_collector,
        )

    if provider_name == "pyttsx3":
        return Pyttsx3TextToSpeechProvider(
            streaming=read_config_value(provider_config, "streaming", True),
            diagnostics_collector=diagnostics_collector,
        )

    if provider_name == "piper":
        return PiperTextToSpeechProvider(
            voice=read_config_value(provider_config, "voice", "default"),
            piper_path=read_config_value(provider_config, "piper_path", "piper"),
            model_path=read_config_value(provider_config, "model_path", ""),
            streaming=read_config_value(provider_config, "streaming", True),
            diagnostics_collector=diagnostics_collector,
        )

    return ConsoleTextToSpeechProvider(
        streaming=read_config_value(provider_config, "streaming", True),
        diagnostics_collector=diagnostics_collector,
    )


def resolve_voice_profile(provider_config):
    """Resolve the configured voice profile and local overrides."""
    registry = VoiceRegistry()
    profile = registry.get_profile(read_config_value(provider_config, "voice_profile", "jarvis_default"))
    voice = read_config_value(provider_config, "voice", "")
    if voice == "default":
        voice = ""

    return apply_voice_overrides(
        profile,
        provider=read_config_value(provider_config, "provider", ""),
        voice=voice,
        speed=read_float_config_value(provider_config, "speed", None),
        pitch=read_float_config_value(provider_config, "pitch", None),
        volume=read_float_config_value(provider_config, "volume", None),
        language=read_config_value(provider_config, "language", ""),
    )


def split_text_for_speech(text):
    """Split one response into stream-ready speech chunks."""
    normalized_text = text.replace("\r\n", "\n")
    chunks = []

    for line in normalized_text.split("\n"):
        cleaned_line = line.strip()

        if cleaned_line != "":
            chunks.append(cleaned_line)

    if len(chunks) == 0:
        return [text]

    return chunks


def normalize_speech_chunks(text):
    """Return a list of stream-ready chunks from text or an iterable."""
    if isinstance(text, str):
        return split_text_for_speech(text)

    if isinstance(text, Iterable):
        return [str(chunk).strip() for chunk in text if str(chunk).strip() != ""]

    return [str(text)]


def should_stop_speaking(session):
    """Return whether speech output should stop for this session."""
    if session is None:
        return False

    return session.should_interrupt()


def read_provider_name(provider_config, profile=None):
    """Read provider name from a config object or a raw string."""
    env_provider = os.environ.get("JARVIS_TTS_PROVIDER")
    if env_provider:
        return env_provider

    if isinstance(provider_config, str):
        return provider_config

    provider_name = getattr(provider_config, "provider", "")

    if provider_name != "":
        return provider_name

    if profile is not None:
        return profile.provider

    return "pyttsx3"


def read_stt_provider_name(provider_config):
    """Read STT provider name from env, config object, or raw string."""
    if "JARVIS_STT_PROVIDER" in os.environ:
        env_provider = os.environ.get("JARVIS_STT_PROVIDER", "")
        if env_provider == "":
            return normalize_stt_provider_name(getattr(provider_config, "provider", "mock"))

        return normalize_stt_provider_name(env_provider)

    env_provider = ""
    if env_provider:
        return normalize_stt_provider_name(env_provider)

    env_provider = read_env_file_value("JARVIS_STT_PROVIDER")
    if env_provider:
        return normalize_stt_provider_name(env_provider)

    if isinstance(provider_config, str):
        return normalize_stt_provider_name(provider_config)

    return normalize_stt_provider_name(getattr(provider_config, "provider", "mock"))


def normalize_stt_provider_name(provider_name):
    """Normalize STT provider aliases."""
    if provider_name == "console":
        return "mock"

    return provider_name


def read_stt_config_value(provider_config, key, default):
    """Read one STT provider config value from env or object."""
    env_key = f"JARVIS_STT_{key.upper()}"
    env_value = os.environ.get(env_key)

    if env_value is None and key == "max_record_seconds":
        env_value = os.environ.get("JARVIS_STT_MAX_SECONDS")

    if env_value is None and key == "min_record_seconds":
        env_value = os.environ.get("JARVIS_STT_MIN_SECONDS")

    if env_value:
        return env_value

    config_value = getattr(provider_config, key, default)

    if config_value != default:
        return config_value

    if env_value is None:
        env_value = read_env_file_value(env_key)

    if env_value == "" and key == "max_record_seconds":
        env_value = read_env_file_value("JARVIS_STT_MAX_SECONDS")

    if env_value == "" and key == "min_record_seconds":
        env_value = read_env_file_value("JARVIS_STT_MIN_SECONDS")

    if env_value:
        return env_value

    return config_value


def read_stt_float_config_value(provider_config, key, default):
    """Read one float STT config value from env or object."""
    value = read_stt_config_value(provider_config, key, default)

    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def read_stt_bool_config_value(provider_config, key, default):
    """Read one boolean STT config value from env or object."""
    value = read_stt_config_value(provider_config, key, default)

    if isinstance(value, bool):
        return value

    return str(value).lower() in ["1", "true", "yes", "on"]


def read_config_value(provider_config, key, default):
    """Read one provider config value from env or object."""
    env_key = f"JARVIS_TTS_{key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value:
        if isinstance(default, bool):
            return env_value.lower() in ["1", "true", "yes", "on"]

        return env_value

    return getattr(provider_config, key, default)


def read_float_config_value(provider_config, key, default):
    """Read one TTS float value from env or object."""
    value = read_config_value(provider_config, key, default)

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def log_provider_selected(diagnostics_collector, provider_name):
    """Publish selected TTS provider diagnostics event."""
    if diagnostics_collector is None:
        return

    diagnostics_collector.log_event("voice.provider.selected")


def create_wav_bytes(recording, sample_rate, np):
    """Return mono PCM WAV bytes for a sounddevice recording."""
    pcm = np.asarray(recording, dtype=np.int16)
    buffer = BytesIO()

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())

    return buffer.getvalue()


def record_microphone_wav_bytes(
    sample_rate=16000,
    device="default",
    min_record_seconds=4.0,
    max_record_seconds=20.0,
    silence_timeout=3.0,
    silence_threshold=80,
):
    """Record microphone audio with sounddevice and return WAV bytes or an error string."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as error:
        return f"Microphone input failed: {error}"

    try:
        print(
            "Listening until silence "
            f"(min {float(min_record_seconds):g}s, max {float(max_record_seconds):g}s, "
            f"silence {float(silence_timeout):g}s)..."
        )
        recording, _metadata = record_sounddevice_audio(
            sd=sd,
            np=np,
            sample_rate=sample_rate,
            device=None if device == "default" else device,
            min_record_seconds=min_record_seconds,
            max_record_seconds=max_record_seconds,
            silence_timeout=silence_timeout,
            silence_threshold=silence_threshold,
        )
        audio_data = create_wav_bytes(recording, sample_rate, np)
        keep_stt_audio(audio_data)
        return audio_data
    except Exception as error:
        return f"Microphone input failed: {error}"


def record_sounddevice_audio(
    sd,
    np,
    sample_rate,
    device=None,
    min_record_seconds=4.0,
    max_record_seconds=20.0,
    silence_timeout=3.0,
    silence_threshold=80,
):
    """Record audio and emit the standard STT recording trace."""
    recording, recording_metadata = record_until_silence(
        sd=sd,
        np=np,
        sample_rate=sample_rate,
        device=device,
        min_record_seconds=min_record_seconds,
        max_record_seconds=max_record_seconds,
        silence_timeout=silence_timeout,
        silence_threshold=silence_threshold,
        return_metadata=True,
    )
    trace_event(
        "voice.stt.recording.completed",
        end_reason=recording_metadata["end_reason"],
        recorded_seconds=recording_metadata["recorded_seconds"],
        speech_started=recording_metadata["speech_started"],
        max_rms=recording_metadata["max_rms"],
        max_dbfs=recording_metadata["max_dbfs"],
        speech_start_elapsed=recording_metadata["speech_start_elapsed"],
        speech_start_dbfs=recording_metadata["speech_start_dbfs"],
    )
    return recording, recording_metadata


def record_until_silence(
    sd,
    np,
    sample_rate,
    device=None,
    min_record_seconds=4.0,
    max_record_seconds=20.0,
    silence_timeout=3.0,
    silence_threshold=80,
    chunk_seconds=0.2,
    return_metadata=False,
):
    """Record chunks until speech is followed by silence or max time is reached."""
    chunk_frames = max(1, int(sample_rate * chunk_seconds))
    max_chunks = max(1, math.ceil(max_record_seconds / chunk_seconds))
    min_chunks = max(1, math.ceil(min_record_seconds / chunk_seconds))
    silence_chunks_required = max(1, math.ceil(silence_timeout / chunk_seconds))
    chunks = []
    silent_chunks = 0
    speech_started = False
    end_reason = "max_seconds"
    noise_floor_dbfs = None
    max_rms = 0.0
    max_dbfs = -120.0
    speech_start_elapsed = 0.0
    speech_start_dbfs = -120.0

    for chunk_index in range(max_chunks):
        chunk = sd.rec(
            chunk_frames,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
        )
        sd.wait()
        chunks.append(chunk)

        rms = calculate_audio_rms(chunk, np)
        dbfs = calculate_dbfs(rms)
        max_rms = max(max_rms, rms)
        max_dbfs = max(max_dbfs, dbfs)
        noise_floor_dbfs = update_noise_floor(noise_floor_dbfs, dbfs, speech_started)
        is_speech = is_speech_chunk(
            rms=rms,
            dbfs=dbfs,
            noise_floor_dbfs=noise_floor_dbfs,
            rms_threshold=silence_threshold,
        )

        if is_speech:
            if not speech_started:
                speech_start_elapsed = round((chunk_index + 1) * chunk_seconds, 3)
                speech_start_dbfs = round(dbfs, 2)
                trace_event(
                    "voice.stt.speech_started",
                    speech_started=True,
                    level=round(rms / 32768.0, 4),
                    rms=round(rms, 2),
                    dbfs=speech_start_dbfs,
                    noise_floor_dbfs=round(noise_floor_dbfs, 2),
                    elapsed=speech_start_elapsed,
                )

            speech_started = True
            silent_chunks = 0
        elif speech_started:
            silent_chunks += 1
        else:
            silent_chunks = 0

        enough_audio = chunk_index + 1 >= min_chunks
        enough_silence = speech_started and silent_chunks >= silence_chunks_required

        if enough_audio and enough_silence:
            end_reason = "silence_timeout"
            break

    if len(chunks) == 0:
        recording = np.zeros((0, 1), dtype=np.int16)
    else:
        recording = np.concatenate(chunks, axis=0)

    if not return_metadata:
        return recording

    return recording, {
        "end_reason": end_reason,
        "recorded_seconds": round(recording.shape[0] / sample_rate, 3) if sample_rate else 0.0,
        "speech_started": speech_started,
        "max_rms": round(max_rms, 2),
        "max_dbfs": round(max_dbfs, 2),
        "speech_start_elapsed": speech_start_elapsed,
        "speech_start_dbfs": speech_start_dbfs,
    }


def calculate_audio_rms(recording, np):
    """Return root mean square volume for an int16 audio chunk."""
    samples = np.asarray(recording, dtype=np.float32)

    if samples.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(samples * samples)))


def calculate_dbfs(rms):
    """Return an RMS level in dBFS for int16 audio."""
    if rms <= 0:
        return -120.0

    return 20.0 * math.log10(min(rms / 32768.0, 1.0))


def update_noise_floor(noise_floor_dbfs, dbfs, speech_started):
    """Track a conservative pre-speech noise floor."""
    if speech_started:
        return noise_floor_dbfs if noise_floor_dbfs is not None else dbfs

    if noise_floor_dbfs is None:
        return dbfs

    return min(noise_floor_dbfs, dbfs)


def is_speech_chunk(rms, dbfs, noise_floor_dbfs, rms_threshold=80, min_dbfs=-55.0, noise_margin_db=8.0):
    """Return whether one audio chunk likely contains speech."""
    adaptive_threshold = noise_floor_dbfs + noise_margin_db if noise_floor_dbfs is not None else min_dbfs
    dbfs_threshold = max(min_dbfs, adaptive_threshold)
    rms_floor = min(float(rms_threshold), 120.0)

    return rms >= rms_floor or dbfs >= dbfs_threshold


def remove_file_if_exists(path):
    """Remove a generated temporary file when it exists."""
    if path is None:
        return

    try:
        os.remove(path)
    except OSError:
        return


def should_keep_tts_audio():
    """Return whether generated TTS files should be kept for debugging."""
    value = os.environ.get("JARVIS_KEEP_TTS_AUDIO", "")

    if value == "":
        value = read_env_file_value("JARVIS_KEEP_TTS_AUDIO")

    return value.lower() in ["1", "true", "yes", "on"]


def transcribe_confirmation_audio(audio_data, client_factory=None, api_key_reader=None):
    """Transcribe a short confirmation clip with OpenAI as a fallback."""
    if not should_use_openai_confirmation_stt():
        return ""

    return transcribe_stt_audio(
        audio_data,
        model=read_confirmation_stt_model(),
        language=read_confirmation_stt_language(),
        provider="openai_confirmation",
        reason="confirmation_fallback",
        client_factory=client_factory,
        api_key_reader=api_key_reader,
        legacy_trace_prefix="voice.stt.confirmation_fallback",
    )


def transcribe_stt_audio(
    audio_data,
    model="gpt-4o-transcribe",
    language="ko",
    provider="openai",
    reason="primary",
    prompt_context="",
    client_factory=None,
    api_key_reader=None,
    legacy_trace_prefix="",
):
    """Transcribe WAV bytes through OpenAI and return normalized text."""
    api_key_reader = api_key_reader or read_openai_tts_api_key
    api_key = api_key_reader()

    if api_key == "":
        result = TranscriptResult(
            success=False,
            provider=provider,
            model=model,
            language=normalize_openai_stt_language(language),
            error_code="missing_api_key",
            error_message="OPENAI_API_KEY is not configured.",
            fallback_used=provider != "openai",
        )
        record_stt_result(result)
        trace_event(
            "voice.stt.openai.skipped",
            provider=provider,
            reason="missing_api_key",
        )
        if legacy_trace_prefix:
            trace_event(
                f"{legacy_trace_prefix}.skipped",
                provider="openai",
                reason="missing_api_key",
            )
        return ""

    audio_path = ""
    started = perf_counter()

    try:
        client = create_openai_client(api_key, client_factory=client_factory)
        output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio_path = output_file.name
        output_file.write(audio_data)
        output_file.close()

        request_language = normalize_openai_stt_language(language)
        prompt = build_openai_stt_prompt(prompt_context)
        logprobs_enabled = is_openai_stt_logprobs_enabled()
        trace_event(
            "voice.stt.openai.started",
            provider=provider,
            model=model,
            language=request_language,
            reason=reason,
            prompt_context=prompt_context,
        )
        if legacy_trace_prefix:
            trace_event(f"{legacy_trace_prefix}.started", provider="openai", model=model)

        with open(audio_path, "rb") as file:
            request = {
                "model": model,
                "file": file,
                "language": request_language,
            }

            if prompt != "":
                request["prompt"] = prompt

            if logprobs_enabled:
                request["include"] = ["logprobs"]

            try:
                response = client.audio.transcriptions.create(**request)
            except Exception:
                if not logprobs_enabled and prompt == "":
                    raise

                file.seek(0)
                if logprobs_enabled:
                    request.pop("include", None)
                    trace_event(
                        "voice.stt.openai.compatibility_retry",
                        provider=provider,
                        model=model,
                        removed="include",
                    )

                    try:
                        response = client.audio.transcriptions.create(**request)
                    except Exception:
                        if prompt == "":
                            raise

                        file.seek(0)
                        request.pop("prompt", None)
                        trace_event(
                            "voice.stt.openai.compatibility_retry",
                            provider=provider,
                            model=model,
                            removed="prompt",
                        )
                        response = client.audio.transcriptions.create(**request)
                else:
                    request.pop("prompt", None)
                    trace_event(
                        "voice.stt.openai.compatibility_retry",
                        provider=provider,
                        model=model,
                        removed="prompt",
                    )
                    response = client.audio.transcriptions.create(**request)

        text = extract_transcription_text(response)
        transcription_metadata = extract_transcription_metadata(response)
        latency_ms = int((perf_counter() - started) * 1000)
        result = TranscriptResult(
            success=text != "",
            text=text,
            raw_text=text,
            normalized_text=text,
            provider=provider,
            model=model,
            language=request_language,
            latency_ms=latency_ms,
            fallback_used=provider != "openai",
            error_code="" if text else "empty_transcript",
            error_message="" if text else "OpenAI STT returned an empty transcript.",
            confidence=transcription_metadata.get("confidence"),
            metadata=transcription_metadata,
        )
        record_stt_result(result)
        trace_event(
            "voice.stt.openai.finished",
            provider=provider,
            success=text != "",
            text=text,
            latency_ms=latency_ms,
            avg_logprob=transcription_metadata.get("avg_logprob"),
            min_logprob=transcription_metadata.get("min_logprob"),
            low_confidence_tokens=transcription_metadata.get("low_confidence_tokens", []),
        )
        if legacy_trace_prefix:
            trace_event(f"{legacy_trace_prefix}.finished", provider="openai", success=text != "", text=text)
        return text
    except Exception as error:
        latency_ms = int((perf_counter() - started) * 1000)
        result = TranscriptResult(
            success=False,
            provider=provider,
            model=model,
            language=normalize_openai_stt_language(language),
            latency_ms=latency_ms,
            fallback_used=provider != "openai",
            error_code=error.__class__.__name__,
            error_message=str(error),
        )
        record_stt_result(result)
        trace_event(
            "voice.stt.openai.failed",
            provider=provider,
            reason=reason,
            error=str(error),
            latency_ms=latency_ms,
        )
        if legacy_trace_prefix:
            trace_event(f"{legacy_trace_prefix}.failed", provider="openai", error=str(error))
        return ""
    finally:
        remove_file_if_exists(audio_path)


def is_short_stt_text(text):
    """Return whether a transcript is short enough to be worth STT verification."""
    cleaned = " ".join(str(text or "").strip().split())

    if cleaned == "":
        return True

    if len(cleaned) <= 8:
        return True

    return len(cleaned.split()) <= 3


def normalize_openai_stt_language(language):
    """Return the language code expected by OpenAI transcription."""
    language_text = str(language or "").strip()
    normalized = language_text.lower().replace("_", "-")

    if normalized == "ko-kr":
        return "ko"

    return language_text or "ko"


def read_openai_stt_prompt():
    """Return a small Korean transcription prompt for OpenAI STT."""
    value = os.environ.get("JARVIS_STT_OPENAI_PROMPT", "")

    if value == "":
        value = read_env_file_value("JARVIS_STT_OPENAI_PROMPT")

    if value.lower() in ["off", "false", "none", "disabled"]:
        return ""

    if value != "":
        return value

    return (
        "한국어 음성입니다. 한국어로 받아쓰세요. "
        "짧은 확인 응답은 응, 네, 예, 아니오, 취소로 받아쓰세요. "
        "자주 나오는 이름은 아야, 유이, 유리입니다. "
        "자주 나오는 장소는 서울역, 잠실, 강릉, 롯데월드, 고용보험공단입니다."
    )


def build_openai_stt_prompt(prompt_context=""):
    """Return the OpenAI STT prompt with short runtime context appended."""
    base_prompt = read_openai_stt_prompt()
    context = str(prompt_context or "").strip()

    if context == "":
        return base_prompt

    if base_prompt == "":
        return context

    return f"{base_prompt} 현재 문맥: {context}"


def is_openai_stt_logprobs_enabled():
    """Return whether OpenAI STT should request token logprobs when supported."""
    value = os.environ.get("JARVIS_STT_LOGPROBS_ENABLED", "")

    if value == "":
        value = read_env_file_value("JARVIS_STT_LOGPROBS_ENABLED")

    return value.lower() in ["1", "true", "yes", "on"]


def extract_transcription_metadata(response):
    """Extract optional confidence/logprob metadata from transcription responses."""
    logprobs = getattr(response, "logprobs", None)

    if isinstance(response, dict):
        logprobs = response.get("logprobs", logprobs)

    values = []
    low_confidence_tokens = []

    for item in normalize_logprob_items(logprobs):
        token = str(item.get("token", "") or item.get("text", "") or "")
        value = item.get("logprob", item.get("avg_logprob", None))

        if value is None:
            continue

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        values.append(numeric)

        if numeric < -1.0 and token:
            low_confidence_tokens.append(token)

    if not values:
        return {}

    avg_logprob = round(sum(values) / len(values), 4)
    min_logprob = round(min(values), 4)
    confidence = round(max(0.0, min(1.0, math.exp(avg_logprob))), 4)

    return {
        "avg_logprob": avg_logprob,
        "min_logprob": min_logprob,
        "confidence": confidence,
        "low_confidence_tokens": tuple(low_confidence_tokens[:8]),
    }


def normalize_logprob_items(logprobs):
    """Return iterable dict-like logprob items from several SDK shapes."""
    if logprobs is None:
        return ()

    if isinstance(logprobs, dict):
        items = logprobs.get("content", logprobs.get("tokens", ()))
    else:
        items = getattr(logprobs, "content", getattr(logprobs, "tokens", logprobs))

    normalized = []

    for item in items or ():
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append(
                {
                    "token": getattr(item, "token", getattr(item, "text", "")),
                    "logprob": getattr(item, "logprob", getattr(item, "avg_logprob", None)),
                }
            )

    return tuple(normalized)


def should_use_openai_confirmation_stt():
    """Return whether confirmation-mode STT should fallback to OpenAI."""
    value = os.environ.get("JARVIS_CONFIRMATION_STT_PROVIDER", "")

    if value == "":
        value = read_env_file_value("JARVIS_CONFIRMATION_STT_PROVIDER")

    if value == "":
        value = "openai"

    return value.lower() in ["openai", "1", "true", "yes", "on"]


def read_confirmation_stt_model():
    """Return the OpenAI model for confirmation fallback STT."""
    value = os.environ.get("JARVIS_CONFIRMATION_STT_MODEL", "")

    if value == "":
        value = read_env_file_value("JARVIS_CONFIRMATION_STT_MODEL")

    return value or "gpt-4o-transcribe"


def read_confirmation_stt_language():
    """Return the language code for confirmation fallback STT."""
    value = os.environ.get("JARVIS_CONFIRMATION_STT_LANGUAGE", "")

    if value == "":
        value = read_env_file_value("JARVIS_CONFIRMATION_STT_LANGUAGE")

    return value or "ko"


def create_openai_client(api_key, client_factory=None):
    """Create an OpenAI client for STT fallback."""
    if client_factory is not None:
        return client_factory(api_key)

    from openai import OpenAI

    return OpenAI(api_key=api_key)


def extract_transcription_text(response):
    """Extract text from an OpenAI transcription response."""
    if isinstance(response, dict):
        return str(response.get("text", "") or "").strip()

    return str(getattr(response, "text", "") or "").strip()


def read_openai_tts_api_key():
    """Read OPENAI_API_KEY from environment or local .env."""
    env_key = os.environ.get("OPENAI_API_KEY", "")

    if env_key != "":
        return env_key

    env_path = Path(".env")

    if not env_path.exists():
        return ""

    with env_path.open("r", encoding="utf-8") as file:
        for line in file:
            key, value = parse_env_line(line)

            if key == "OPENAI_API_KEY":
                return value

    return ""


def parse_env_line(line):
    """Parse one simple KEY=VALUE line."""
    stripped_line = line.strip()

    if stripped_line == "" or stripped_line.startswith("#") or "=" not in stripped_line:
        return "", ""

    key, value = stripped_line.split("=", 1)
    return key.strip(), clean_env_value(value)


def clean_env_value(value):
    """Remove simple wrapping quotes from an env value."""
    cleaned_value = value.strip()

    if len(cleaned_value) >= 2 and cleaned_value[0] == cleaned_value[-1]:
        if cleaned_value[0] in ["'", '"']:
            return cleaned_value[1:-1]

    return cleaned_value


def create_temp_audio_path(response_format):
    """Create a temporary audio path for one TTS response."""
    suffix = f".{response_format}"

    if should_keep_tts_audio():
        return create_kept_tts_audio_path(suffix)

    output_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    output_file.close()
    return output_file.name


def create_kept_tts_audio_path(suffix):
    """Create a stable project-local TTS debug path."""
    output_dir = Path("output") / "tts"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid4().hex[:6]
    return str(output_dir / f"tts_{timestamp}_{unique_id}{suffix}")


def keep_stt_audio(audio_data):
    """Keep microphone STT audio for deterministic replay when enabled."""
    if not should_keep_stt_audio():
        return ""

    output_path = create_kept_stt_audio_path()
    write_bytes(output_path, audio_data)
    trace_event(
        "voice.stt.audio_saved",
        path=output_path,
        size=len(audio_data),
    )
    return output_path


def should_keep_stt_audio():
    """Return whether recorded STT audio should be kept for replay."""
    value = os.environ.get("JARVIS_KEEP_STT_AUDIO", "")

    if value == "":
        value = read_env_file_value("JARVIS_KEEP_STT_AUDIO")

    return value.lower() in ["1", "true", "yes", "on"]


def create_kept_stt_audio_path():
    """Create a stable project-local STT debug path."""
    output_dir = Path("output") / "stt"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid4().hex[:6]
    return str(output_dir / f"stt_{timestamp}_{unique_id}.wav")


def write_speech_response(response, path):
    """Write an OpenAI speech response to a local file."""
    if hasattr(response, "write_to_file"):
        response.write_to_file(path)
        return

    if hasattr(response, "stream_to_file"):
        response.stream_to_file(path)
        return

    if hasattr(response, "read"):
        write_bytes(path, response.read())
        return

    content = getattr(response, "content", None)

    if content is not None:
        write_bytes(path, content)
        return

    raise RuntimeError("OpenAI TTS response did not include writable audio content.")


def write_bytes(path, content):
    """Write bytes-like content to a file."""
    with open(path, "wb") as file:
        file.write(content)


def is_suspicious_tts_duration(text, duration_sec, format_error=""):
    """Return whether a generated TTS file is unexpectedly short."""
    if format_error:
        return False

    try:
        duration = float(duration_sec)
    except (TypeError, ValueError):
        return False

    if duration <= 0:
        return False

    text_length = len(str(text or "").strip())

    if text_length < 8:
        return False

    minimum_expected = min(1.0, text_length * 0.05)
    return duration < minimum_expected
