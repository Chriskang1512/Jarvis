from jarvis.commands import CommandDispatcher, create_default_registry
from jarvis.chat import ChatService, ProviderFactory, PromptBuilder, create_default_prompt_profile
from jarvis.config import ConfigurationLoader
from jarvis.events import EventBus
from jarvis.events.adapters import ConsoleEventAdapter


def main():
    """Run the Jarvis command console loop."""
    config = ConfigurationLoader().load()
    event_bus = EventBus()
    console_adapter = ConsoleEventAdapter()
    event_bus.subscribe_all(console_adapter.handle_event)
    prompt_profile = create_default_prompt_profile()
    prompt_builder = PromptBuilder(profile=prompt_profile)
    chat_provider = ProviderFactory().create(config)
    chat_service = ChatService(provider=chat_provider, prompt_builder=prompt_builder)
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
            break


if __name__ == "__main__":
    main()
