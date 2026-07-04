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
)
