from jarvis.commands import CommandDispatcher, create_default_registry
from jarvis.events import EventBus
from jarvis.events.adapters import ConsoleEventAdapter


def main():
    """Run the Jarvis command console loop."""
    event_bus = EventBus()
    console_adapter = ConsoleEventAdapter()
    event_bus.subscribe_all(console_adapter.handle_event)
    registry = create_default_registry()
    dispatcher = CommandDispatcher(registry=registry, event_bus=event_bus)

    print("================================")
    print("Jarvis v0.2.0-alpha.2")
    print("================================")

    while True:
        user_command = input("Jarvis > ").strip()
        response = dispatcher.dispatch(user_command)

        print(response)
        print("--------------------------")

        if dispatcher.should_exit():
            break


if __name__ == "__main__":
    main()
