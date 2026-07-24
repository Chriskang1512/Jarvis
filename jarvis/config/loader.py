import json
import os
from pathlib import Path

from jarvis.config.settings import AIIntentConfig, CalendarConfig, ContactsConfig, ConversationConfig, JarvisConfig, MailConfig, MemoryStoreConfig, STTConfig
from jarvis.config.settings import TTSConfig
from jarvis.config.settings import WeatherConfig


CONFIG_FILE = Path("config.json")


class ConfigurationLoader:
    """Load JarvisConfig from config.json or safe defaults."""

    def __init__(self, path=CONFIG_FILE):
        """Create a loader for one configuration file path."""
        self.path = path

    def load(self):
        """Return JarvisConfig from config.json, or defaults if missing."""
        if not self.path.exists():
            return JarvisConfig()

        config_data = read_json_file(self.path)
        return create_config_from_dict(config_data)


def read_json_file(path):
    """Read JSON configuration data from a file."""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def create_config_from_dict(config_data):
    """Create JarvisConfig using known keys from a dictionary."""
    tts_data = config_data.get("tts", {})
    stt_data = config_data.get("stt", {})
    conversation_data = config_data.get("conversation", {})
    memory_store_data = config_data.get("memory_store", {})
    weather_data = config_data.get("weather", {})
    calendar_data = config_data.get("calendar", {})
    contacts_data = config_data.get("contacts", {})
    mail_data = config_data.get("mail", {})
    ai_intent_data = config_data.get("ai_intent", {})

    chat_provider = config_data.get("chat_provider", config_data.get("provider", "mock"))

    return JarvisConfig(
        provider=chat_provider,
        chat_provider=chat_provider,
        model=config_data.get("model", "mock"),
        temperature=config_data.get("temperature", 0.7),
        debug=config_data.get("debug", False),
        profile=config_data.get("profile", "jarvis"),
        version=config_data.get("version", "v0.4.0"),
        tts=create_tts_config(config_data, tts_data),
        stt=create_stt_config(stt_data),
        conversation=create_conversation_config(conversation_data),
        memory_store=create_memory_store_config(memory_store_data),
        weather=create_weather_config(weather_data),
        calendar=create_calendar_config(calendar_data),
        contacts=create_contacts_config(contacts_data),
        mail=create_mail_config(mail_data),
        ai_intent=create_ai_intent_config(ai_intent_data),
    )


def create_tts_config(config_data, tts_data):
    """Create TTSConfig using known keys from a dictionary."""
    provider = config_data.get("tts_provider", tts_data.get("provider", "pyttsx3"))
    voice_profile = config_data.get("voice_profile", tts_data.get("voice_profile", "jarvis_default"))

    return TTSConfig(
        provider=provider,
        voice_profile=voice_profile,
        voice=tts_data.get("voice", "default"),
        speed=tts_data.get("speed", 1.0),
        pitch=tts_data.get("pitch", 0),
        volume=tts_data.get("volume", 1.0),
        language=tts_data.get("language", "ko"),
        openai_model=tts_data.get("openai_model", "gpt-4o-mini-tts"),
        response_format=tts_data.get("response_format", "wav"),
        streaming=tts_data.get("streaming", True),
        piper_path=tts_data.get("piper_path", "piper"),
        model_path=tts_data.get("model_path", ""),
    )


def create_stt_config(stt_data):
    """Create STTConfig using known keys from a dictionary."""
    return STTConfig(
        provider=stt_data.get("provider", "openai"),
        language=stt_data.get("language", "ko-KR"),
        device=stt_data.get("device", "default"),
        openai_model=stt_data.get("openai_model", "gpt-4o-transcribe"),
        openai_language=stt_data.get("openai_language", "ko"),
        min_record_seconds=stt_data.get("min_record_seconds", 4.0),
        max_record_seconds=stt_data.get("max_record_seconds", 20.0),
        silence_timeout=stt_data.get("silence_timeout", 3.0),
    )


def create_conversation_config(conversation_data):
    """Create ConversationConfig using known keys from a dictionary."""
    return ConversationConfig(
        max_turns=conversation_data.get("max_turns", 6),
        max_tokens=conversation_data.get("max_tokens", 1200),
        follow_up_timeout=conversation_data.get("follow_up_timeout", 8.0),
    )


def create_memory_store_config(memory_store_data):
    """Create MemoryStoreConfig using known keys from a dictionary."""
    return MemoryStoreConfig(
        path=memory_store_data.get("path", "data/memory_store.json"),
    )


def create_weather_config(weather_data):
    """Create WeatherConfig using known keys from a dictionary."""
    return WeatherConfig(
        provider=weather_data.get("provider", "mock"),
        fallback_to_mock=weather_data.get("fallback_to_mock", True),
        openweather_lang=weather_data.get("openweather_lang", "kr"),
        default_location=os.getenv(
            "JARVIS_WEATHER_DEFAULT_LOCATION",
            weather_data.get("default_location", "강릉"),
        ),
    )


def create_calendar_config(calendar_data):
    """Create CalendarConfig using known keys from config and env."""
    return CalendarConfig(
        provider=os.getenv("JARVIS_CALENDAR_PROVIDER", calendar_data.get("provider", "mock")),
        allow_mock_fallback=calendar_data.get("allow_mock_fallback", True),
        timezone=os.getenv("JARVIS_CALENDAR_TIMEZONE", calendar_data.get("timezone", "Asia/Seoul")),
        google_credentials_path=os.getenv(
            "JARVIS_GOOGLE_TOKEN_PATH",
            calendar_data.get("google_credentials_path", "data/credentials/google_token.json"),
        ),
        google_client_secret_path=os.getenv(
            "JARVIS_GOOGLE_CLIENT_SECRET_PATH",
            calendar_data.get("google_client_secret_path", "client_secret.json"),
        ),
    )


def create_contacts_config(contacts_data):
    """Create ContactsConfig using known keys from config and env."""
    return ContactsConfig(
        provider=os.getenv("JARVIS_CONTACTS_PROVIDER", contacts_data.get("provider", "memory")),
        google_credentials_path=os.getenv(
            "JARVIS_GOOGLE_TOKEN_PATH",
            contacts_data.get("google_credentials_path", "data/credentials/google_token.json"),
        ),
        google_client_secret_path=os.getenv(
            "JARVIS_GOOGLE_CLIENT_SECRET_PATH",
            contacts_data.get("google_client_secret_path", "client_secret.json"),
        ),
    )


def create_mail_config(mail_data):
    """Create MailConfig using known keys from config and env."""
    return MailConfig(
        provider=os.getenv("JARVIS_MAIL_PROVIDER", mail_data.get("provider", "mock")),
        google_credentials_path=os.getenv(
            "JARVIS_GOOGLE_TOKEN_PATH",
            mail_data.get("google_credentials_path", "data/credentials/google_token.json"),
        ),
        google_client_secret_path=os.getenv(
            "JARVIS_GOOGLE_CLIENT_SECRET_PATH",
            mail_data.get("google_client_secret_path", "client_secret.json"),
        ),
    )


def create_ai_intent_config(ai_intent_data):
    """Create AIIntentConfig using known keys from a dictionary."""
    return AIIntentConfig(
        enabled=ai_intent_data.get("enabled", False),
        provider=ai_intent_data.get("provider", "openai"),
        model=ai_intent_data.get("model", ""),
        timeout=ai_intent_data.get("timeout", 8.0),
        min_confidence=ai_intent_data.get("min_confidence", 0.70),
        max_output_tokens=ai_intent_data.get("max_output_tokens", 300),
        reasoning_effort=ai_intent_data.get("reasoning_effort", "minimal"),
        verbosity=ai_intent_data.get("verbosity", "low"),
    )
