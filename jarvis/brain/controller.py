from jarvis.agents.invest import handle_invest_command
from jarvis.agents.japanese_shorts import handle_japanese_shorts_command
from jarvis.agents.memory import handle_memory_command
from jarvis.agents.music_youtube import handle_music_youtube_command
from jarvis.agents.scheduler import handle_scheduler_command
from jarvis.memory.store import save_memory


AGENT_KEYWORDS = {
    "memory": ["기억", "메모", "저장"],
    "scheduler": ["일정", "예약", "스케줄"],
    "invest": ["주식", "투자", "SCHD", "VOO", "QQQ"],
    "japanese": ["일본어", "니혼고", "번역", "쇼츠"],
    "music": ["음악", "유튜브", "노래"],
}

ROUTING_PRIORITY = ["memory", "scheduler", "invest", "japanese", "music"]

AGENT_HANDLERS = {
    "memory": handle_memory_command,
    "scheduler": handle_scheduler_command,
    "invest": handle_invest_command,
    "japanese": handle_japanese_shorts_command,
    "music": handle_music_youtube_command,
}


def handle_command(command):
    """Analyze a user command and send it to the right agent."""
    save_memory("user", command)

    if command == "":
        response = "Please type a command."
    elif has_keyword(command, ["help", "도움말"]):
        response = get_help_message()
    else:
        agent_name = find_agent_name(command)
        response = route_to_agent(agent_name, command)

    save_memory("jarvis", response)
    return response


def find_agent_name(command):
    """Find the first matching agent name using the routing priority."""
    for agent_name in ROUTING_PRIORITY:
        keywords = AGENT_KEYWORDS[agent_name]

        if has_keyword(command, keywords):
            return agent_name

    return "brain"


def route_to_agent(agent_name, command):
    """Send the user command to the selected agent handler."""
    if agent_name == "brain":
        return get_brain_default_message()

    handler = AGENT_HANDLERS[agent_name]
    return handler(command)


def has_keyword(command, keywords):
    """Check whether the user command contains one of the target keywords."""
    lowered_command = command.lower()

    for keyword in keywords:
        if keyword.lower() in lowered_command:
            return True

    return False


def get_help_message():
    """Return a simple list of commands the beginner CLI can understand."""
    return (
        "사용 가능한 예시: 주식 분석, 일본어 쇼츠 만들기, 음악 유튜브, "
        "기억해 내 이름은 Chris야, 메모 보여줘, 일정 예약"
    )


def get_brain_default_message():
    """Return the default Brain response when no agent keyword matches."""
    return "Selected Agent: Brain. 아직 어떤 Agent에게 보낼지 확실하지 않습니다."
