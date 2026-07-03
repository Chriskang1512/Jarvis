import sys

from jarvis.commands import CommandDispatcher, create_default_registry
from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.config import ConfigurationLoader
from jarvis.events import EventBus
from jarvis.events.adapters import ConsoleEventAdapter
from jarvis.memory import ConversationContext, MemoryService, MockMemoryProvider


def main():
    """Run the Jarvis command console loop."""
    configure_console_encoding()
    config = ConfigurationLoader().load()
    event_bus = EventBus()
    console_adapter = ConsoleEventAdapter()
    event_bus.subscribe_all(console_adapter.handle_event)
    prompt_profile = create_default_prompt_profile()
    prompt_builder = PromptBuilder(profile=prompt_profile)
    chat_provider = ProviderFactory().create(config)
    memory_service = MemoryService(provider=MockMemoryProvider())
    conversation_context = ConversationContext(
        max_turns=config.conversation.max_turns,
        max_tokens=config.conversation.max_tokens,
    )
    chat_service = ChatService(
        provider=chat_provider,
        prompt_builder=prompt_builder,
        memory_service=memory_service,
        conversation_context=conversation_context,
    )
    registry = create_default_registry()
    dispatcher = CommandDispatcher(
        registry=registry,
        event_bus=event_bus,
        chat_service=chat_service,
        config=config,
    )

    print("================================")
    print(f"Jarvis {config.version}")
    print("================================")

    if config.debug:
        print(f"Provider: {config.provider}")
        print(f"Model: {config.model}")
        print("--------------------------")

    while True:
        user_command = input("Jarvis > ").strip()
        response = dispatcher.dispatch(user_command)

        print(response)
        print("--------------------------")

        if dispatcher.should_exit():
            chat_service.finish_conversation()
            break


def configure_console_encoding():
    """Use UTF-8 console input and output when the terminal supports it."""
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
