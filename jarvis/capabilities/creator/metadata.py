from jarvis.capabilities.metadata import CapabilityMetadata


CREATOR_CAPABILITY_METADATA = CapabilityMetadata(
    id="creator",
    name="Creator",
    description="Creative engine capability for reusable AI creation workflows.",
    version="0.1.0-alpha",
    status="alpha",
    owner="Jarvis Team",
    tools=[
        "creator_lyrics",
        "creator_music_prompt",
        "creator_title",
        "creator_description",
        "creator_song_package",
    ],
    planning_prefix="creator",
    planning_aliases=["creator", "youtube", "유튜브", "창작"],
    planning_intents={
        "lyrics": ["lyrics", "가사", "노래"],
        "music prompt": ["music prompt", "suno", "udio", "음악 프롬프트"],
        "title ideas": ["title", "제목"],
        "description": ["description", "설명", "유튜브 설명"],
        "song package": ["song package", "노래 패키지"],
    },
    planning_examples=[
        "유튜브 설명 만들어줘",
        "노래 가사 만들어줘",
        "제목 추천",
    ],
)
