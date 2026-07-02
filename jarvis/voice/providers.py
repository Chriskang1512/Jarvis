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


class ConsoleTextToSpeechProvider:
    """Console fallback provider for testing text-to-speech output."""

    def speak(self, text):
        """Print speech text to the console."""
        print(f"Jarvis says: {text}")


class Pyttsx3TextToSpeechProvider:
    """Local TTS provider using pyttsx3."""

    def speak(self, text):
        """Speak text using the local pyttsx3 engine."""
        try:
            import pyttsx3
        except ImportError:
            print("pyttsx3 package is not installed.")
            print(f"Jarvis says: {text}")
            return

        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()


def create_stt_provider(provider_name):
    """Create a speech-to-text provider by name."""
    if provider_name == "microphone":
        return MicrophoneSpeechToTextProvider()

    return ConsoleSpeechToTextProvider()


def create_tts_provider(provider_name):
    """Create a text-to-speech provider by name."""
    if provider_name == "pyttsx3":
        return Pyttsx3TextToSpeechProvider()

    return ConsoleTextToSpeechProvider()
