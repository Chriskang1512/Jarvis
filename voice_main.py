import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.brain import IntentRuntime
from jarvis.config import ConfigurationLoader
from jarvis.abilities.native.weather.provider import read_env_value
from jarvis.debug_trace import is_debug_trace_enabled, read_env_file_value
from jarvis.debug_trace import trace_event
from jarvis.diagnostics import DiagnosticsCollector, RuntimeDevConsole
from jarvis.memory import MemoryService, MockMemoryProvider
from jarvis.native.reminder import ReminderEngine, ReminderScheduler
from jarvis.native.reminder.registry import set_default_reminder_engine
from jarvis.llm.factory import create_llm_provider
from jarvis.runtime.intent import AIIntentParser, HybridIntentParser
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import create_default_tool_registry
from jarvis.voice import (
    VoicePipeline,
    WakeWordListener,
    create_stt_provider,
    create_tts_provider,
    create_voice_session,
)
from jarvis.voice.playback import read_playback_backend_name
from jarvis.voice.providers import read_stt_provider_name, should_keep_tts_audio
from jarvis.voice.stt import is_stt_metrics_enabled


def main():
    """Run the Jarvis voice pipeline."""
    configure_console_encoding()
    configure_logging()
    trace_event(
        "voice.startup",
        cwd=os.getcwd(),
        debug_trace=True,
        keep_tts_audio=should_keep_tts_audio(),
    )

    config = ConfigurationLoader().load()
    print_runtime_banner(config)
    diagnostics_collector = DiagnosticsCollector()
    voice_session = create_voice_session(
        max_turns=config.conversation.max_turns,
        max_tokens=config.conversation.max_tokens,
    )
    prompt_builder = PromptBuilder(profile=create_default_prompt_profile())
    chat_provider = ProviderFactory(diagnostics_collector=diagnostics_collector).create(config)
    memory_service = MemoryService(provider=MockMemoryProvider())
    stt_provider = create_stt_provider(config.stt)
    tts_provider = create_tts_provider(config.tts, diagnostics_collector=diagnostics_collector)
    reminder_engine = ReminderEngine(notification_callback=tts_provider.speak)
    set_default_reminder_engine(reminder_engine)
    reminder_scheduler = ReminderScheduler(reminder_engine)
    tool_registry = create_default_tool_registry(
        diagnostics_collector=diagnostics_collector,
        memory_service=memory_service,
        config=config,
    )
    tool_dispatcher = RuntimeToolDispatcher(
        registry=tool_registry,
        diagnostics_collector=diagnostics_collector,
        intent_parser=create_runtime_intent_parser(config),
    )
    intent_runtime = IntentRuntime(
        tool_dispatcher=tool_dispatcher,
        diagnostics_collector=diagnostics_collector,
    )
    chat_service = ChatService(
        provider=chat_provider,
        prompt_builder=prompt_builder,
        memory_service=memory_service,
        voice_session=voice_session,
        diagnostics_collector=diagnostics_collector,
    )

    wake_word = os.environ.get("JARVIS_WAKE_WORD", "hey jarvis")
    pipeline = VoicePipeline(
        wake_listener=WakeWordListener(wake_word=wake_word),
        stt_provider=stt_provider,
        chat_service=chat_service,
        tts_provider=tts_provider,
        diagnostics_collector=diagnostics_collector,
        voice_session=voice_session,
        intent_runtime=intent_runtime,
        runtime_console=create_runtime_console(config),
        follow_up_timeout=config.conversation.follow_up_timeout,
    )

    print("Jarvis Voice Pipeline")
    print(f"Wake word: {wake_word}")
    print(f"Voice session: {voice_session.session_id}")
    print("Press Ctrl+C to stop.")

    reminder_scheduler.start()

    try:
        if os.environ.get("JARVIS_VOICE_ONCE") == "true":
            pipeline.run_once()
            chat_service.finish_conversation()
            return

        while True:
            pipeline.run_once()
    finally:
        reminder_scheduler.stop()


def configure_logging():
    """Configure logging for every voice pipeline stage."""
    level = logging.DEBUG if os.environ.get("JARVIS_VOICE_DEBUG") == "true" else logging.INFO
    log_dir = Path("output") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "jarvis_voice.log", encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=log_format, handlers=handlers, force=True)


def print_runtime_banner(config):
    """Print a concise runtime visibility banner."""
    print("========== Jarvis Runtime ==========")
    print(f"Debug Trace      : {on_off(is_debug_trace_enabled())}")
    print(f"Weather Provider : {config.weather.provider}")
    print(f"Weather Location : {config.weather.default_location}")
    print(f"OpenWeather Key  : Loaded ({yes_no(read_env_value('OPENWEATHER_API_KEY') != '')})")
    print(f"Fallback         : {on_off(config.weather.fallback_to_mock)}")
    print(f"TTS Provider     : {config.tts.provider}")
    print(f"TTS Speed        : {config.tts.speed}")
    print(f"STT Provider     : {read_stt_provider_name(config.stt)}")
    print(f"STT OpenAI Model : {get_stt_openai_model(config)}")
    print(f"STT Language     : {get_stt_openai_language(config)}")
    print(f"STT Fallback     : {get_stt_fallback_label(config)}")
    print(f"Context Correct  : {on_off(is_stt_context_correction_enabled())}")
    print(f"STT Metrics      : {on_off(is_stt_metrics_enabled())}")
    print(f"Keep TTS Audio   : {on_off(should_keep_tts_audio())}")
    print(f"Playback Backend : {read_playback_backend_name() or 'auto'}")
    print(f"AI Intent Parser : {on_off(is_ai_intent_enabled(config))}")
    print(f"AI Intent Force  : {on_off(is_ai_intent_force_enabled())}")
    print(f"AI Intent MaxTok : {get_ai_intent_max_output_tokens(config)}")
    print("====================================")


def on_off(value):
    """Format bool as ON/OFF."""
    return "ON" if bool(value) else "OFF"


def yes_no(value):
    """Format bool as YES/NO."""
    return "YES" if bool(value) else "NO"


def create_runtime_console(config):
    """Create the runtime dev console only when debugging is enabled."""
    enabled = config.debug or os.environ.get("JARVIS_RUNTIME_CONSOLE") == "true"

    if not enabled:
        return None

    return RuntimeDevConsole()


def create_runtime_intent_parser(config):
    """Create optional AI Intent Parser for the runtime dispatcher."""
    if not is_ai_intent_enabled(config):
        return None

    try:
        provider = create_llm_provider(
            IntentProviderConfig(
                provider=get_intent_provider_name(config),
                model=get_intent_model_name(config),
                temperature=0.0,
            )
        )
    except Exception:
        provider = None

    return HybridIntentParser(
        ai_parser=AIIntentParser(
            provider=provider,
            model=get_intent_model_name(config),
            enabled=provider is not None,
            timeout_seconds=config.ai_intent.timeout,
            min_confidence=config.ai_intent.min_confidence,
            max_output_tokens=get_ai_intent_max_output_tokens(config),
            reasoning_effort=get_ai_intent_reasoning_effort(config),
            verbosity=get_ai_intent_verbosity(config),
        )
    )


@dataclass
class IntentProviderConfig:
    """Small config adapter for LLMProviderFactory."""

    provider: str
    model: str
    temperature: float = 0.0


def is_ai_intent_enabled(config):
    """Return whether AI Intent Parser should be enabled."""
    env_value = os.environ.get("JARVIS_AI_INTENT_ENABLED", "")

    if env_value != "":
        return env_value.lower() in ["1", "true", "yes", "on"]

    return bool(config.ai_intent.enabled)


def get_intent_provider_name(config):
    """Return configured intent provider name."""
    return os.environ.get("JARVIS_INTENT_PROVIDER", config.ai_intent.provider or config.chat_provider)


def get_intent_model_name(config):
    """Return configured intent model name."""
    return os.environ.get("JARVIS_INTENT_MODEL", config.ai_intent.model or config.model)


def is_ai_intent_force_enabled():
    """Return whether AI Intent Parser should run before rule planning."""
    return os.environ.get("JARVIS_AI_INTENT_FORCE", "").lower() in ["1", "true", "yes", "on"]


def get_ai_intent_max_output_tokens(config):
    """Return output token cap for AI Intent Parser."""
    return int(os.environ.get("JARVIS_AI_INTENT_MAX_OUTPUT_TOKENS", config.ai_intent.max_output_tokens or 300))


def get_ai_intent_reasoning_effort(config):
    """Return reasoning effort for AI Intent Parser provider calls."""
    return os.environ.get("JARVIS_AI_INTENT_REASONING_EFFORT", config.ai_intent.reasoning_effort or "minimal")


def get_ai_intent_verbosity(config):
    """Return output verbosity for AI Intent Parser provider calls."""
    return os.environ.get("JARVIS_AI_INTENT_VERBOSITY", config.ai_intent.verbosity or "low")


def get_stt_openai_model(config):
    """Return configured OpenAI STT model for runtime visibility."""
    return (
        os.environ.get("JARVIS_STT_OPENAI_MODEL")
        or read_env_file_value("JARVIS_STT_OPENAI_MODEL")
        or config.stt.openai_model
        or "gpt-4o-transcribe"
    )


def get_stt_openai_language(config):
    """Return configured OpenAI STT language for runtime visibility."""
    return (
        os.environ.get("JARVIS_STT_OPENAI_LANGUAGE")
        or read_env_file_value("JARVIS_STT_OPENAI_LANGUAGE")
        or getattr(config.stt, "openai_language", "")
        or "ko"
    )


def get_stt_fallback_label(config):
    """Return configured STT fallback visibility label."""
    provider = read_stt_provider_name(config.stt).lower()

    if provider == "hybrid":
        return "openai"

    if provider == "microphone" and is_stt_fallback_enabled(config):
        return "openai"

    return "OFF"


def is_stt_fallback_enabled(config):
    """Return whether the microphone STT provider may fallback to OpenAI."""
    value = os.environ.get("JARVIS_STT_FALLBACK_ENABLED", "")

    if value == "":
        value = read_env_file_value("JARVIS_STT_FALLBACK_ENABLED")

    if value == "":
        value = str(getattr(config.stt, "fallback_enabled", False))

    return value.lower() in ["1", "true", "yes", "on"]


def is_stt_context_correction_enabled():
    """Return whether STT text correction is enabled."""
    value = os.environ.get("JARVIS_STT_CONTEXT_CORRECTION", "")

    if value == "":
        value = read_env_file_value("JARVIS_STT_CONTEXT_CORRECTION")

    if value == "":
        return True

    return value.lower() in ["1", "true", "yes", "on"]


def configure_console_encoding():
    """Use UTF-8 console input and output when the terminal supports it."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
