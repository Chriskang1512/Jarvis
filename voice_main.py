import logging
import os
import sys

from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.config import ConfigurationLoader
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.memory import MemoryService, MockMemoryProvider
from jarvis.voice import (
    VoicePipeline,
    WakeWordListener,
    create_stt_provider,
    create_tts_provider,
    create_voice_session,
)


def main():
    """Run the Jarvis voice pipeline."""
    configure_console_encoding()
    configure_logging()

    config = ConfigurationLoader().load()
    diagnostics_collector = DiagnosticsCollector()
    voice_session = create_voice_session(
        max_turns=config.conversation.max_turns,
        max_tokens=config.conversation.max_tokens,
    )
    prompt_builder = PromptBuilder(profile=create_default_prompt_profile())
    chat_provider = ProviderFactory(diagnostics_collector=diagnostics_collector).create(config)
    memory_service = MemoryService(provider=MockMemoryProvider())
    chat_service = ChatService(
        provider=chat_provider,
        prompt_builder=prompt_builder,
        memory_service=memory_service,
        voice_session=voice_session,
        diagnostics_collector=diagnostics_collector,
    )

    wake_word = os.environ.get("JARVIS_WAKE_WORD", "hey jarvis")
    stt_provider_name = os.environ.get("JARVIS_STT_PROVIDER", "console")

    pipeline = VoicePipeline(
        wake_listener=WakeWordListener(wake_word=wake_word),
        stt_provider=create_stt_provider(stt_provider_name),
        chat_service=chat_service,
        tts_provider=create_tts_provider(config.tts, diagnostics_collector=diagnostics_collector),
        diagnostics_collector=diagnostics_collector,
        voice_session=voice_session,
    )

    print("Jarvis Voice Pipeline")
    print(f"Wake word: {wake_word}")
    print(f"Voice session: {voice_session.session_id}")
    print("Press Ctrl+C to stop.")

    if os.environ.get("JARVIS_VOICE_ONCE") == "true":
        pipeline.run_once()
        chat_service.finish_conversation()
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
