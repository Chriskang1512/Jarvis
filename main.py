import os
import sys

from jarvis.commands import CommandDispatcher, create_default_registry
from jarvis.capabilities import CapabilityLoader
from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.config import ConfigurationLoader
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.dashboard import DashboardBackend, DashboardEventBridge, ObservabilityHub
from jarvis.debug_trace import subscribe_trace, unsubscribe_trace
from jarvis.events import EventBus
from jarvis.events.adapters import ConsoleEventAdapter
from jarvis.input import InputManager, KeyboardInputProvider
from jarvis.memory import ConversationContext, MemoryService, MockMemoryProvider
from jarvis.memory_store import JsonMemoryStore, MemoryManager
from jarvis.permissions import PermissionLayer
from jarvis.plugins import PluginLoader
from jarvis.tools import ToolDispatcher, create_default_tool_registry


def main():
    """Run the Jarvis command console loop."""
    configure_console_encoding()
    config = ConfigurationLoader().load()
    event_bus = EventBus()
    observability_hub = ObservabilityHub()
    dashboard_bridge = DashboardEventBridge(observability_hub)
    event_bus.subscribe_all(dashboard_bridge.handle_event)
    trace_observer = subscribe_trace(
        lambda event, payload: observability_hub.record(event, payload)
    )
    diagnostics_collector = DiagnosticsCollector()
    console_adapter = ConsoleEventAdapter()
    event_bus.subscribe_all(console_adapter.handle_event)
    prompt_profile = create_default_prompt_profile()
    prompt_builder = PromptBuilder(profile=prompt_profile)
    chat_provider = ProviderFactory(diagnostics_collector=diagnostics_collector).create(config)
    memory_service = MemoryService(provider=MockMemoryProvider())
    memory_manager = MemoryManager(
        store=JsonMemoryStore(config.memory_store.path),
        diagnostics_collector=diagnostics_collector,
    )
    memory_manager.load()
    tool_registry = create_default_tool_registry(
        diagnostics_collector=diagnostics_collector,
        memory_service=memory_service,
        memory_manager=memory_manager,
    )
    plugin_loader = PluginLoader(diagnostics_collector=diagnostics_collector)
    plugin_registry = plugin_loader.load()
    plugin_loader.register_plugin_tools(plugin_registry, tool_registry)
    capability_loader = CapabilityLoader(
        diagnostics_collector=diagnostics_collector,
        memory_manager=memory_manager,
    )
    capability_registry = capability_loader.load()
    capability_loader.register_capability_tools(capability_registry, tool_registry)
    tool_dispatcher = ToolDispatcher(
        registry=tool_registry,
        permission_layer=PermissionLayer(diagnostics_collector=diagnostics_collector),
        diagnostics_collector=diagnostics_collector,
    )
    conversation_context = ConversationContext(
        max_turns=config.conversation.max_turns,
        max_tokens=config.conversation.max_tokens,
    )
    chat_service = ChatService(
        provider=chat_provider,
        prompt_builder=prompt_builder,
        memory_service=memory_service,
        conversation_context=conversation_context,
        diagnostics_collector=diagnostics_collector,
    )
    registry = create_default_registry()
    dispatcher = CommandDispatcher(
        registry=registry,
        event_bus=event_bus,
        chat_service=chat_service,
        tool_dispatcher=tool_dispatcher,
        config=config,
    )
    input_manager = InputManager()
    keyboard_provider = KeyboardInputProvider()
    dashboard = None
    if os.getenv("JARVIS_DASHBOARD", "true").lower() not in {"0", "false", "off", "no"}:
        dashboard = DashboardBackend(
            hub=observability_hub,
            memory_manager=memory_manager,
            diagnostics_collector=diagnostics_collector,
            plugin_registry=plugin_registry,
            ability_registry=capability_registry,
        ).start()
        observability_hub.runtime.update(
            {
                "current_session": diagnostics_collector.get_snapshot().session.session_id,
                "current_provider": config.provider,
            }
        )

    print("================================")
    print(f"Jarvis {config.version}")
    if dashboard is not None:
        print(f"Dashboard {dashboard.url}")
    print("================================")

    if config.debug:
        print(f"Provider: {config.provider}")
        print(f"Model: {config.model}")
        print("--------------------------")

    while True:
        keyboard_provider.submit(input("Jarvis > ").strip())
        input_envelope = input_manager.ingest(keyboard_provider)
        response = dispatcher.dispatch(str(input_envelope.content or ""))

        print(response)
        print("--------------------------")

        if dispatcher.should_exit():
            chat_service.finish_conversation()
            if dashboard is not None:
                dashboard.stop()
            unsubscribe_trace(trace_observer)
            break


def configure_console_encoding():
    """Use UTF-8 console input and output when the terminal supports it."""
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
