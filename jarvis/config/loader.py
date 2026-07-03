import json
from pathlib import Path

from jarvis.config.settings import JarvisConfig
from jarvis.config.settings import TTSConfig


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

    return JarvisConfig(
        provider=config_data.get("provider", "mock"),
        model=config_data.get("model", "mock"),
        temperature=config_data.get("temperature", 0.7),
        debug=config_data.get("debug", False),
        profile=config_data.get("profile", "jarvis"),
        version=config_data.get("version", "v0.3.0-beta.1"),
        tts=create_tts_config(tts_data),
    )


def create_tts_config(tts_data):
    """Create TTSConfig using known keys from a dictionary."""
    return TTSConfig(
        provider=tts_data.get("provider", "console"),
        voice=tts_data.get("voice", "default"),
        streaming=tts_data.get("streaming", True),
        piper_path=tts_data.get("piper_path", "piper"),
        model_path=tts_data.get("model_path", ""),
    )
