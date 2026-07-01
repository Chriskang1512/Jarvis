from jarvis.brain.controller import handle_command


def run_assistant():
    """Run a simple assistant example for older code that imports this file."""
    print("Hello, Jarvis")
    print(handle_command("help"))
