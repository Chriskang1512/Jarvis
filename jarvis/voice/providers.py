import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol


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


class MicrophoneSpeechToTextProvider:
    """Microphone STT provider using the SpeechRecognition package."""

    def listen(self):
        """Listen through the microphone and return recognized text."""
        try:
            import speech_recognition as sr
        except ImportError:
            return "SpeechRecognition package is not installed."

        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                print("Listening...")
                audio = recognizer.listen(source)
        except Exception as error:
            return f"Microphone input failed: {error}"

        try:
            return recognizer.recognize_google(audio)
        except Exception as error:
            return f"Speech recognition failed: {error}"


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
        self.log_event("voice.tts.started")
        self.log_event("voice.tts.playback.started")
        print(f"Jarvis says: {text}")
        self.log_event("voice.tts.playback.completed")

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


def create_stt_provider(provider_name):
    """Create a speech-to-text provider by name."""
    if provider_name == "microphone":
        return MicrophoneSpeechToTextProvider()

    return ConsoleSpeechToTextProvider()


def create_tts_provider(provider_config, diagnostics_collector=None):
    """Create a text-to-speech provider by name."""
    provider_name = read_provider_name(provider_config)

    log_provider_selected(diagnostics_collector, provider_name)

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


def read_provider_name(provider_config):
    """Read provider name from a config object or a raw string."""
    env_provider = os.environ.get("JARVIS_TTS_PROVIDER")
    if env_provider:
        return env_provider

    if isinstance(provider_config, str):
        return provider_config

    return getattr(provider_config, "provider", "pyttsx3")


def read_config_value(provider_config, key, default):
    """Read one provider config value from env or object."""
    env_key = f"JARVIS_TTS_{key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value:
        if isinstance(default, bool):
            return env_value.lower() in ["1", "true", "yes", "on"]

        return env_value

    return getattr(provider_config, key, default)


def log_provider_selected(diagnostics_collector, provider_name):
    """Publish selected TTS provider diagnostics event."""
    if diagnostics_collector is None:
        return

    diagnostics_collector.log_event("voice.provider.selected")


def find_executable(executable):
    """Resolve an executable path using PATH or a direct file path."""
    if Path(executable).exists():
        return executable

    return shutil.which(executable)


def play_wav_file(path):
    """Play a WAV file with the local OS when supported."""
    try:
        import winsound
    except ImportError:
        print(f"Piper audio generated: {path}")
        return

    winsound.PlaySound(path, winsound.SND_FILENAME)


def remove_file_if_exists(path):
    """Remove a generated temporary file when it exists."""
    if path is None:
        return

    try:
        os.remove(path)
    except OSError:
        return
