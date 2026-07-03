import logging
import os
import sys

from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.config import ConfigurationLoader
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.memory import MemoryService, MockMemoryProvider
from jarvis.voice import VoicePipeline, WakeWordListener, create_stt_provider, create_tts_provider


def main():
    """Run the Jarvis voice pipeline."""
    configure_console_encoding()
    configure_logging()

    config = ConfigurationLoader().load()
    diagnostics_collector = DiagnosticsCollector()
    prompt_builder = PromptBuilder(profile=create_default_prompt_profile())
    chat_provider = ProviderFactory().create(config)
    memory_service = MemoryService(provider=MockMemoryProvider())
    chat_service = ChatService(
        provider=chat_provider,
        prompt_builder=prompt_builder,
        memory_service=memory_service,
    )

    wake_word = os.environ.get("JARVIS_WAKE_WORD", "hey jarvis")
    stt_provider_name = os.environ.get("JARVIS_STT_PROVIDER", "console")
    tts_provider_name = os.environ.get("JARVIS_TTS_PROVIDER", "console")

    pipeline = VoicePipeline(
        wake_listener=WakeWordListener(wake_word=wake_word),
        stt_provider=create_stt_provider(stt_provider_name),
        chat_service=chat_service,
        tts_provider=create_tts_provider(tts_provider_name),
        diagnostics_collector=diagnostics_collector,
    )

    print("Jarvis Voice Pipeline")
    print(f"Wake word: {wake_word}")
    print("Press Ctrl+C to stop.")

    if os.environ.get("JARVIS_VOICE_ONCE") == "true":
        pipeline.run_once()
        return

    while True:
        pipeline.run_once()


def configure_logging():
    """Configure logging for every voice pipeline stage."""
    level = logging.DEBUG if os.environ.get("JARVIS_VOICE_DEBUG") == "true" else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def configure_console_encoding():
    """Use UTF-8 console input and output when the terminal supports it."""
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
