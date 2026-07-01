from jarvis.agents.invest import handle_invest_command
from jarvis.agents.japanese_shorts import handle_japanese_shorts_command
from jarvis.agents.music_youtube import handle_music_youtube_command
from jarvis.memory.store import save_memory


def handle_command(command):
    """Analyze a user command and send it to the right agent."""
    save_memory("user", command)

    lowered_command = command.lower()

    if lowered_command == "":
        response = "Please type a command."
    elif "invest" in lowered_command or "stock" in lowered_command:
        response = handle_invest_command(command)
    elif "japanese" in lowered_command or "shorts" in lowered_command:
        response = handle_japanese_shorts_command(command)
    elif "music" in lowered_command or "youtube" in lowered_command:
        response = handle_music_youtube_command(command)
    elif "help" in lowered_command:
        response = get_help_message()
    else:
        response = "I received your command. I will learn how to handle it soon."

    save_memory("jarvis", response)
    return response


def get_help_message():
    """Return a simple list of commands the beginner CLI can understand."""
    return (
        "Try commands like: help, invest report, japanese shorts idea, "
        "or music youtube upload."
    )
