from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6"


@dataclass
class ChatResponseMetadata:
    """Store optional provider response metadata for future analytics."""

    text: str = ""
    model: str = ""
    provider_name: str = ""
    finish_reason: str = ""
    usage: object = None
    created_at: str = ""


class ChatProvider(Protocol):
    """Interface for future chat providers such as OpenAI or Claude."""

    def generate_reply(self, message):
        """Generate one reply for a user message."""
        ...


class MockChatProvider:
    """Simple local chat provider used before real AI APIs are connected."""

    def __init__(self):
        """Create a mock provider with empty response metadata."""
        self.last_metadata = ChatResponseMetadata(
            model="mock",
            provider_name="mock",
            created_at=current_timestamp(),
        )

    def generate_reply(self, message):
        """Return a fixed response without using network or API keys."""
        if message.strip() == "":
            reply = "무엇을 이야기할까요?"
            self.last_metadata = create_mock_metadata(reply)
            return reply

        reply = "안녕하세요.\n저는 Jarvis입니다."
        self.last_metadata = create_mock_metadata(reply)
        return reply


class OpenAIProvider:
    """Chat provider that sends completed prompts to OpenAI."""

    def __init__(self, model, temperature, env_path=".env"):
        """Create an OpenAI provider with runtime settings."""
        self.model = choose_openai_model(model)
        self.temperature = temperature
        self.env_path = Path(env_path)
        self.last_metadata = ChatResponseMetadata(
            model=self.model,
            provider_name="openai",
            created_at=current_timestamp(),
        )

    def generate_reply(self, message):
        """Return one real OpenAI response for a completed prompt."""
        api_key = read_openai_api_key(self.env_path)

        if api_key == "":
            return create_missing_openai_key_message()

        try:
            from openai import OpenAI
        except ImportError:
            return "openai 패키지가 설치되어 있지 않습니다. pip install -r requirements.txt 를 실행해주세요."

        client = OpenAI(api_key=api_key)
        try:
            response = create_openai_response(
                client=client,
                model=self.model,
                message=message,
                temperature=self.temperature,
            )
        except Exception as error:
            return create_openai_error_message(error)

        self.last_metadata = create_openai_metadata(response)
        return response.output_text


class ClaudeProvider:
    """Chat provider that sends completed prompts to Claude."""

    def __init__(self, model, temperature, env_path=".env"):
        """Create a Claude provider with runtime settings."""
        self.model = choose_claude_model(model)
        self.temperature = temperature
        self.env_path = Path(env_path)
        self.last_metadata = ChatResponseMetadata(
            model=self.model,
            provider_name="claude",
            created_at=current_timestamp(),
        )

    def generate_reply(self, message):
        """Return one real Claude response for a completed prompt."""
        api_key = read_claude_api_key(self.env_path)

        if api_key == "":
            return create_missing_claude_key_message()

        try:
            from anthropic import Anthropic
        except ImportError:
            return "anthropic 패키지가 설치되어 있지 않습니다. pip install -r requirements.txt 를 실행해주세요."

        client = Anthropic(api_key=api_key)

        try:
            response = create_claude_response(
                client=client,
                model=self.model,
                message=message,
                temperature=self.temperature,
            )
        except Exception as error:
            return create_claude_error_message(error)

        reply = extract_claude_text(response)
        self.last_metadata = create_claude_metadata(response, reply)
        return reply


def create_openai_response(client, model, message, temperature):
    """Create an OpenAI response with model-safe request parameters."""
    request_data = {
        "model": model,
        "input": message,
    }

    if should_send_temperature(model):
        request_data["temperature"] = temperature

    return client.responses.create(**request_data)


def should_send_temperature(model):
    """Return whether the selected model should receive temperature."""
    return not model.startswith("gpt-5")


def create_openai_error_message(error):
    """Return a friendly message for OpenAI API errors."""
    return "\n".join(
        [
            "OpenAI provider failed to generate a response.",
            "",
            f"Reason: {error}",
            "",
            "You can switch provider=mock while checking the setup.",
        ]
    )


def create_openai_metadata(response):
    """Create response metadata from an OpenAI SDK response object."""
    return ChatResponseMetadata(
        text=getattr(response, "output_text", ""),
        model=getattr(response, "model", ""),
        provider_name="openai",
        finish_reason=getattr(response, "finish_reason", ""),
        usage=getattr(response, "usage", None),
        created_at=current_timestamp(),
    )


def create_claude_response(client, model, message, temperature):
    """Create a Claude response with the Messages API."""
    return client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=temperature,
        messages=[
            {
                "role": "user",
                "content": message,
            }
        ],
    )


def extract_claude_text(response):
    """Extract text from a Claude Messages API response."""
    text_parts = []

    for content_block in getattr(response, "content", []):
        text = getattr(content_block, "text", "")

        if text != "":
            text_parts.append(text)

    return "\n".join(text_parts)


def create_claude_metadata(response, reply):
    """Create response metadata from a Claude SDK response object."""
    return ChatResponseMetadata(
        text=reply,
        model=getattr(response, "model", ""),
        provider_name="claude",
        finish_reason=getattr(response, "stop_reason", ""),
        usage=getattr(response, "usage", None),
        created_at=current_timestamp(),
    )


def create_missing_claude_key_message():
    """Return a friendly setup message when the Claude API key is missing."""
    return "\n".join(
        [
            "Claude provider selected, but ANTHROPIC_API_KEY was not found.",
            "",
            "Please add ANTHROPIC_API_KEY to your .env file or switch provider=mock.",
        ]
    )


def create_claude_error_message(error):
    """Return a friendly message for Claude API errors."""
    return "\n".join(
        [
            "Claude provider failed to generate a response.",
            "",
            f"Reason: {error}",
            "",
            "You can switch provider=mock while checking the setup.",
        ]
    )


def create_missing_openai_key_message():
    """Return a friendly setup message when the OpenAI API key is missing."""
    return "\n".join(
        [
            "OpenAI provider selected, but OPENAI_API_KEY was not found.",
            "",
            "Please create a .env file or switch provider=mock.",
        ]
    )


def create_mock_metadata(reply):
    """Create response metadata for a mock provider reply."""
    return ChatResponseMetadata(
        text=reply,
        model="mock",
        provider_name="mock",
        created_at=current_timestamp(),
    )


def current_timestamp():
    """Return the current local timestamp as a simple ISO string."""
    return datetime.now().isoformat(timespec="seconds")


def read_openai_api_key(env_path):
    """Read OPENAI_API_KEY from a local .env file."""
    env_values = read_env_file(env_path)
    return env_values.get("OPENAI_API_KEY", "")


def read_claude_api_key(env_path):
    """Read ANTHROPIC_API_KEY from a local .env file."""
    env_values = read_env_file(env_path)
    return env_values.get("ANTHROPIC_API_KEY", "")


def choose_openai_model(model):
    """Choose a safe OpenAI model when config only selects provider=openai."""
    if model == "" or model == "mock":
        return DEFAULT_OPENAI_MODEL

    return model


def choose_claude_model(model):
    """Choose a safe Claude model when config only selects provider=claude."""
    if model == "" or model == "mock" or model.startswith("gpt-"):
        return DEFAULT_CLAUDE_MODEL

    return model


def read_env_file(env_path):
    """Read simple KEY=VALUE lines from a .env file."""
    if not env_path.exists():
        return {}

    values = {}

    with env_path.open("r", encoding="utf-8") as file:
        for line in file:
            key, value = parse_env_line(line)

            if key != "":
                values[key] = value

    return values


def parse_env_line(line):
    """Parse one simple KEY=VALUE environment line."""
    stripped_line = line.strip()

    if stripped_line == "" or stripped_line.startswith("#"):
        return "", ""

    if "=" not in stripped_line:
        return "", ""

    key, value = stripped_line.split("=", 1)
    return key.strip(), clean_env_value(value)


def clean_env_value(value):
    """Remove simple wrapping quotes from an environment value."""
    cleaned_value = value.strip()

    if len(cleaned_value) >= 2 and cleaned_value[0] == cleaned_value[-1]:
        if cleaned_value[0] in ["'", '"']:
            return cleaned_value[1:-1]

    return cleaned_value
