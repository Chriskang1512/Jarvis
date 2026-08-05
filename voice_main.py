import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.capability_planning import (
    CapabilityRegistryAdapter,
    HybridPlanner,
    NativePlanningCoordinator,
)
from jarvis.brain import IntentRuntime
from jarvis.config import ConfigurationLoader
from jarvis.abilities.native.weather.provider import read_env_value
from jarvis.dashboard import (
    DashboardBackend,
    DashboardEventBridge,
    DashboardProjectionEngine,
    ObservabilityHub,
    SafeDashboardProjectionHandler,
    SQLiteDashboardProjectionRepository,
)
from jarvis.debug_trace import is_debug_trace_enabled, read_env_file_value
from jarvis.debug_trace import subscribe_trace, trace_event, unsubscribe_trace
from jarvis.diagnostics import DiagnosticsCollector, RuntimeDevConsole
from jarvis.core.events import InMemoryEventBus
from jarvis.graph_execution import CapabilityExecutionAdapter, GraphExecutor
from jarvis.artifacts import ArtifactManager, SQLiteArtifactRepository
from jarvis.execution_memory import (
    ExecutionMemoryService,
    SQLiteExecutionMemoryRepository,
)
from jarvis.memory import (
    MemoryManager,
    MemoryService,
    MockMemoryProvider,
    SQLiteMemoryProvider,
)
from jarvis.native.reminder import ReminderEngine, ReminderScheduler
from jarvis.native.reminder.registry import set_default_reminder_engine
from jarvis.llm.factory import create_llm_provider
from jarvis.runtime.intent import AIIntentParser, HybridIntentParser
from jarvis.runtime import JarvisRuntimeService
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import create_default_tool_registry
from jarvis.voice import (
    VoicePipeline,
    create_stt_provider,
    create_tts_provider,
    create_voice_session,
)
from jarvis.voice.playback import read_playback_backend_name
from jarvis.voice.providers import (
    read_stt_provider_name,
    should_keep_tts_audio,
    transcribe_stt_audio,
)
from jarvis.voice.stt import is_stt_metrics_enabled
from jarvis.wake import (
    ApiWakeProvider,
    ClapWakeProvider,
    ClapDetector,
    ClapDetectorSettings,
    KeyboardWakeProvider,
    MicrophoneWakeWordProvider,
    MobileWakeProvider,
    TouchPortalWakeProvider,
    WakeManager,
    WakeMethod,
    WakeProfile,
    WakeSettings,
    SoundDeviceClapMonitor,
)


def main():
    """Run the Jarvis voice pipeline."""
    configure_console_encoding()
    configure_logging()
    observability_hub = ObservabilityHub()
    trace_observer = subscribe_trace(
        lambda event, payload: observability_hub.record(event, payload)
    )
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
    event_bus = InMemoryEventBus()
    event_bus.subscribe("*", DashboardEventBridge(observability_hub).handle_event)
    projection_repository = SQLiteDashboardProjectionRepository(
        config.memory_store.sqlite_path
    )
    projection_engine = DashboardProjectionEngine(projection_repository)
    event_bus.subscribe(
        "*",
        SafeDashboardProjectionHandler(
            projection_engine,
            publish=observability_hub.publish_projection,
        ).handle_event,
    )
    memory_manager = MemoryManager(
        provider=SQLiteMemoryProvider(config.memory_store.sqlite_path),
        session_id=voice_session.session_id,
        event_bus=event_bus,
        default_source="user",
        default_source_provider=config.stt.provider,
        default_origin="voice",
        default_created_by="user",
    )
    stt_provider = create_stt_provider(
        replace(
            config.stt,
            openai_language=get_stt_openai_language(config),
        )
    )
    tts_provider = create_tts_provider(config.tts, diagnostics_collector=diagnostics_collector)
    reminder_engine = ReminderEngine(notification_callback=tts_provider.speak)
    set_default_reminder_engine(reminder_engine)
    reminder_scheduler = ReminderScheduler(reminder_engine)
    tool_registry = create_default_tool_registry(
        diagnostics_collector=diagnostics_collector,
        memory_service=memory_service,
        config=config,
    )
    native_execution_enabled = is_native_execution_enabled()
    capability_snapshot = CapabilityRegistryAdapter().create_snapshot(
        tool_registry.ability_registry,
        environment_constraints={
            "conversationId": voice_session.session_id,
            "nativeExecutionEnabled": native_execution_enabled,
        },
    )
    artifact_repository = SQLiteArtifactRepository(
        config.memory_store.sqlite_path
    )
    graph_executor = GraphExecutor(
        CapabilityExecutionAdapter(tool_registry.ability_registry),
        event_bus=event_bus,
        execution_memory=ExecutionMemoryService(
            SQLiteExecutionMemoryRepository(
                config.memory_store.sqlite_path
            )
        ),
        artifact_manager=ArtifactManager(artifact_repository),
        verification_enabled=is_native_reliability_enabled(
            "JARVIS_NATIVE_VERIFICATION_ENABLED", default=True
        ),
        retry_enabled=is_native_reliability_enabled(
            "JARVIS_NATIVE_RETRY_ENABLED", default=False
        ),
        replan_enabled=is_native_reliability_enabled(
            "JARVIS_NATIVE_REPLAN_ENABLED", default=False
        ),
    )
    native_planning_coordinator = NativePlanningCoordinator(
        capability_snapshot,
        planner=HybridPlanner(),
        user_preferences={"location": config.weather.default_location},
        native_execution_enabled=native_execution_enabled,
        graph_executor=graph_executor,
    )
    tool_dispatcher = RuntimeToolDispatcher(
        registry=tool_registry,
        diagnostics_collector=diagnostics_collector,
        intent_parser=create_runtime_intent_parser(config),
        event_bus=event_bus,
        memory_manager=memory_manager,
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
    wake_manager = create_wake_manager(config, wake_word)
    pipeline = VoicePipeline(
        wake_listener=wake_manager,
        stt_provider=stt_provider,
        chat_service=chat_service,
        tts_provider=tts_provider,
        diagnostics_collector=diagnostics_collector,
        voice_session=voice_session,
        intent_runtime=intent_runtime,
        native_planning_coordinator=native_planning_coordinator,
        runtime_console=create_runtime_console(config),
        follow_up_timeout=config.conversation.follow_up_timeout,
    )
    runtime_service = JarvisRuntimeService(
        pipeline=pipeline,
        config=config,
        wake_manager=wake_manager,
    )
    dashboard = None
    if os.getenv("JARVIS_DASHBOARD", "true").lower() not in {"0", "false", "off", "no"}:
        dashboard = DashboardBackend(
            hub=observability_hub,
            memory_manager=memory_manager,
            diagnostics_collector=diagnostics_collector,
            ability_registry=tool_registry.ability_registry,
            runtime_service=runtime_service,
            artifact_repository=artifact_repository,
            projection_repository=projection_repository,
            projection_engine=projection_engine,
        ).start()
        observability_hub.runtime.update(
            {
                "current_session": voice_session.session_id,
                "current_provider": config.provider,
                "wake_method": config.wake.primary,
            }
        )

    print("Jarvis Voice Pipeline")
    print(f"Wake methods: {', '.join(config.wake.methods)}")
    print(f"Wake word: {wake_word}")
    print(f"Voice session: {voice_session.session_id}")
    if dashboard is not None:
        print(f"Dashboard: {dashboard.url}")
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
        memory_manager.clear_working()
        reminder_scheduler.stop()
        if dashboard is not None:
            dashboard.stop()
        unsubscribe_trace(trace_observer)


def create_wake_manager(config, wake_word):
    """Create enabled Wake Providers backed by one shared microphone stream."""
    method_map = {method.value: method for method in WakeMethod}
    enabled = tuple(
        method_map[name]
        for name in config.wake.methods
        if name in method_map
    )
    primary = method_map.get(config.wake.primary)
    priority = tuple(
        dict.fromkeys(
            ([primary] if primary is not None else [])
            + list(enabled)
        )
    )
    phrases = tuple(dict.fromkeys((wake_word,) + tuple(config.wake.voice_phrases)))
    settings = WakeSettings(
        profile=WakeProfile(
            name=config.wake.profile,
            priority=priority,
            enabled=enabled,
        ),
        voice_phrases=phrases,
        keyboard_hotkey=config.wake.keyboard_hotkey,
    )
    clap_provider = ClapWakeProvider(
        detector=ClapDetector(
            ClapDetectorSettings(
                peak_threshold=config.wake.clap_peak_threshold,
                rms_threshold=config.wake.clap_rms_threshold,
                crest_factor_threshold=config.wake.clap_crest_factor_threshold,
                min_gap_seconds=config.wake.clap_min_gap_seconds,
                max_gap_seconds=config.wake.clap_max_gap_seconds,
                settle_seconds=config.wake.clap_settle_seconds,
                second_clap_threshold_ratio=config.wake.clap_second_threshold_ratio,
                release_threshold_ratio=config.wake.clap_release_threshold_ratio,
                noise_floor_multiplier=config.wake.clap_noise_floor_multiplier,
            )
        )
    )
    microphone_monitor = SoundDeviceClapMonitor(
        clap_provider.feed_audio,
        device=None if config.stt.device == "default" else config.stt.device,
    )
    voice_provider = MicrophoneWakeWordProvider(
        phrases,
        transcribe=lambda audio_data: transcribe_stt_audio(
            audio_data,
            model=config.stt.openai_model,
            language=config.stt.openai_language,
            provider="openai_wake",
            reason="wake_phrase",
            prompt_context="호출어: 자비스, 헤이 자비스, hey jarvis",
        ),
        monitor=microphone_monitor,
    )
    clap_provider.monitor = microphone_monitor
    providers = (
        clap_provider,
        voice_provider,
        KeyboardWakeProvider(config.wake.keyboard_hotkey),
        TouchPortalWakeProvider(),
        MobileWakeProvider(),
        ApiWakeProvider(),
    )
    return WakeManager(
        providers,
        settings=settings,
    )


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
    print(f"Calendar Provider: {config.calendar.provider}")
    print(f"Contacts Provider: {config.contacts.provider}")
    print(f"Mail Provider    : {config.mail.provider}")
    print(f"OpenWeather Key  : Loaded ({yes_no(read_env_value('OPENWEATHER_API_KEY') != '')})")
    print(f"Fallback         : {on_off(config.weather.fallback_to_mock)}")
    print(f"TTS Provider     : {config.tts.provider}")
    print(f"TTS Speed        : {config.tts.speed}")
    print(f"STT Provider     : {read_stt_provider_name(config.stt)}")
    print(f"STT OpenAI Model : {get_stt_openai_model(config)}")
    print(f"STT Language     : {get_stt_openai_language(config)}")
    print(
        "Language Policy : "
        f"{str(getattr(getattr(config, 'language', None), 'policy', 'AUTO')).upper()}"
    )
    print(f"STT Fallback     : {get_stt_fallback_label(config)}")
    print(f"Context Correct  : {on_off(is_stt_context_correction_enabled())}")
    print(f"STT Metrics      : {on_off(is_stt_metrics_enabled())}")
    print(
        "Clap Thresholds  : "
        f"peak={config.wake.clap_peak_threshold:.3f} "
        f"rms={config.wake.clap_rms_threshold:.3f} "
        f"crest={config.wake.clap_crest_factor_threshold:.2f}"
    )
    print(f"Keep TTS Audio   : {on_off(should_keep_tts_audio())}")
    print(f"Playback Backend : {read_playback_backend_name() or 'auto'}")
    print(f"AI Intent Parser : {on_off(is_ai_intent_enabled(config))}")
    print(f"Native Execution : {on_off(is_native_execution_enabled())}")
    print(
        "Native Verification : "
        f"{on_off(is_native_reliability_enabled('JARVIS_NATIVE_VERIFICATION_ENABLED', default=True))}"
    )
    print(
        "Native Retry : "
        f"{on_off(is_native_reliability_enabled('JARVIS_NATIVE_RETRY_ENABLED', default=False))}"
    )
    print(
        "Native Replan : "
        f"{on_off(is_native_reliability_enabled('JARVIS_NATIVE_REPLAN_ENABLED', default=False))}"
    )
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


def is_native_execution_enabled():
    """Read the Native Graph feature flag from process env or project .env."""
    value = os.environ.get("JARVIS_NATIVE_EXECUTION_ENABLED", "")
    if value == "":
        value = read_env_file_value("JARVIS_NATIVE_EXECUTION_ENABLED") or ""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_native_reliability_enabled(name, *, default):
    """Read a native reliability feature flag from env or project .env."""
    value = os.environ.get(name, "")
    if value == "":
        value = read_env_file_value(name) or ""
    if value == "":
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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
    """Return the effective primary STT language for runtime visibility."""
    policy = str(
        getattr(getattr(config, "language", None), "policy", "AUTO")
    ).upper()
    if policy == "AUTO":
        return "auto"
    forced = {
        "FORCE_KO": "ko",
        "FORCE_JA": "ja",
        "FORCE_EN": "en",
    }.get(policy)
    if forced:
        return forced
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
