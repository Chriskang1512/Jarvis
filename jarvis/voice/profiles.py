from dataclasses import dataclass, replace


@dataclass(frozen=True)
class VoiceProfile:
    """Describe a reusable Jarvis voice identity."""

    id: str
    display_name: str
    provider: str
    voice: str
    name: str = ""
    speed: float = 1.0
    pitch: int = 0
    volume: float = 1.0
    language: str = "ko"
    accent: str = ""
    emotion: str = ""
    style: str = ""

    def to_dict(self):
        """Return a stable profile payload."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "provider": self.provider,
            "voice": self.voice,
            "name": self.name,
            "speed": self.speed,
            "pitch": self.pitch,
            "volume": self.volume,
            "language": self.language,
            "accent": self.accent,
            "emotion": self.emotion,
            "style": self.style,
        }


class VoiceRegistry:
    """Registry for named voice profiles."""

    def __init__(self, profiles=None):
        """Create a registry with built-in and optional profiles."""
        self.profiles = {}

        for profile in create_default_profiles():
            self.register(profile)

        for profile in profiles or []:
            self.register(profile)

    def register(self, profile):
        """Register one voice profile."""
        self.profiles[profile.id] = profile

    def get_profile(self, profile_id):
        """Return a profile by ID, with friendly aliases."""
        resolved_id = normalize_profile_id(profile_id)

        if resolved_id not in self.profiles:
            raise KeyError(f"Voice profile '{profile_id}' is not registered.")

        return self.profiles[resolved_id]


def create_default_profiles():
    """Return built-in Jarvis voice identities."""
    return [
        VoiceProfile(
            id="jarvis_default",
            display_name="Jarvis",
            provider="openai",
            voice="alloy",
            name="JARVIS-inspired original",
            speed=0.95,
            pitch=0,
            volume=1.0,
            language="ko",
            accent="British-inspired",
            emotion="calm, composed, witty",
            style="private butler / hotel concierge",
        ),
        VoiceProfile(
            id="jarvis_cinematic",
            display_name="Jarvis Cinematic",
            provider="openai",
            voice="onyx",
            name="Cinematic assistant original",
            speed=0.92,
            pitch=0,
            volume=1.0,
            language="ko",
            accent="British-inspired",
            emotion="low, calm, precise, dry wit",
            style="cinematic private AI assistant",
        ),
        VoiceProfile(
            id="friday",
            display_name="Friday",
            provider="openai",
            voice="nova",
            name="Friday original",
            speed=1.0,
            pitch=0,
            volume=1.0,
            language="en",
            accent="neutral",
            emotion="calm, efficient",
            style="executive assistant",
        ),
    ]


def normalize_profile_id(profile_id):
    """Normalize friendly profile aliases."""
    profile_id = str(profile_id or "jarvis_default")
    aliases = {
        "jarvis": "jarvis_default",
        "default": "jarvis_default",
    }
    return aliases.get(profile_id, profile_id)


def apply_voice_overrides(profile, provider="", voice="", speed=None, pitch=None, volume=None, language=""):
    """Return a profile with config-level overrides applied."""
    return replace(
        profile,
        provider=provider or profile.provider,
        voice=voice or profile.voice,
        speed=profile.speed if speed is None else speed,
        pitch=profile.pitch if pitch is None else pitch,
        volume=profile.volume if volume is None else volume,
        language=language or profile.language,
    )
