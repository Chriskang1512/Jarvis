from jarvis.capabilities.metadata import CapabilityMetadata


JAPANESE_CAPABILITY_METADATA = CapabilityMetadata(
    id="japanese",
    name="Japanese",
    description="Japanese study assistant capability.",
    version="0.1.0",
    tools=[
        "japanese_translate",
        "japanese_grammar",
        "japanese_reply",
        "japanese_review",
    ],
)
