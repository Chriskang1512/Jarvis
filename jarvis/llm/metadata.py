from dataclasses import dataclass


@dataclass
class LLMProviderMetadata:
    """Describe one LLM provider and its capabilities."""

    id: str
    name: str
    model: str = ""
    supports_stream: bool = False
    supports_tools: bool = False
    supports_images: bool = False
    supports_reasoning: bool = False
