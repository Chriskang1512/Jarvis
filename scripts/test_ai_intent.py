import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config.loader import ConfigurationLoader
from jarvis.runtime.intent import AIIntentParser, HybridIntentParser, IntentContext
from jarvis.runtime.intent.metrics import get_intent_metrics


def main():
    """Run a safe AI Intent Parser smoke test without executing abilities."""
    args = parse_args()
    config = ConfigurationLoader(Path(args.config)).load()
    parser = create_parser(config, args)
    context = create_context(config)
    metrics = get_intent_metrics()
    metrics.reset()

    for text in args.text:
        result = parser.parse(text, context)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))

    print("Intent Metrics")
    print(json.dumps(metrics.snapshot().to_dict(), ensure_ascii=False, indent=2))


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test Jarvis AI Intent Parser without executing abilities.")
    parser.add_argument("text", nargs="*", help="Text to parse.")
    parser.add_argument("--config", default="config.json", help="Path to Jarvis config file.")
    parser.add_argument("--model", default="", help="Override JARVIS_INTENT_MODEL/config model.")
    parser.add_argument("--provider", default="", help="Override JARVIS_INTENT_PROVIDER/config provider.")
    parser.add_argument("--ai-only", action="store_true", help="Skip rule parser and call AI parser directly.")
    return parser.parse_args()


def create_parser(config, args):
    """Create the requested parser."""
    provider_name = args.provider or os.environ.get("JARVIS_INTENT_PROVIDER", "") or config.ai_intent.provider or config.chat_provider
    model = args.model or os.environ.get("JARVIS_INTENT_MODEL", "") or config.ai_intent.model or config.model
    llm_provider = create_provider(provider_name, model)
    ai_parser = AIIntentParser(
        provider=llm_provider,
        enabled=True,
        model=model,
        timeout_seconds=config.ai_intent.timeout,
        min_confidence=config.ai_intent.min_confidence,
        max_output_tokens=int(os.environ.get("JARVIS_AI_INTENT_MAX_OUTPUT_TOKENS", config.ai_intent.max_output_tokens)),
        reasoning_effort=os.environ.get("JARVIS_AI_INTENT_REASONING_EFFORT", config.ai_intent.reasoning_effort),
        verbosity=os.environ.get("JARVIS_AI_INTENT_VERBOSITY", config.ai_intent.verbosity),
    )

    if args.ai_only:
        return ai_parser

    return HybridIntentParser(ai_parser=ai_parser, min_confidence=config.ai_intent.min_confidence)


def create_provider(provider_name, model):
    """Create a provider without importing runtime factories."""
    if provider_name == "mock":
        return MockProvider(model)

    if provider_name == "openai":
        return DirectOpenAIProvider(model)

    raise ValueError(f"Unsupported intent provider for smoke test: {provider_name}")


def create_context(config):
    """Create a minimal IntentContext for smoke tests."""
    now = datetime.now()
    return IntentContext(
        session_id="manual-ai-intent-test",
        current_date=now.date().isoformat(),
        current_time=now.time().isoformat(timespec="seconds"),
        timezone="Asia/Seoul",
        available_abilities=("weather", "memory", "calendar", "reminder", "integration_n8n"),
        available_actions=(
            "weather.query",
            "memory.remember",
            "memory.recall",
            "memory.forget",
            "memory.list",
            "calendar.create",
            "calendar.list",
            "calendar.update",
            "calendar.delete",
            "reminder.create",
            "reminder.cancel",
            "reminder.list",
            "integration_n8n.health",
            "integration_n8n.execute",
        ),
        user_vocabulary=read_user_vocabulary(),
    )


def read_user_vocabulary():
    """Read optional user vocabulary without failing the smoke test."""
    path = "config/user_vocabulary.json"
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {}


class DirectOpenAIProvider:
    """Minimal OpenAI provider for the smoke test script."""

    def __init__(self, model):
        self.model = model or "gpt-4o-mini"
        self.last_metadata = ProviderMetadata(self.model)

    def generate(self, prompt, **options):
        """Call OpenAI Responses API."""
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("openai package is not installed. Run pip install -r requirements.txt.") from error

        api_key = os.environ.get("OPENAI_API_KEY", "") or read_env_value("OPENAI_API_KEY")
        if api_key == "":
            raise RuntimeError("OPENAI_API_KEY was not found in environment or .env.")

        request_data = {
            "model": self.model,
            "input": prompt,
        }
        apply_generation_options(request_data, options)
        client = OpenAI(api_key=api_key)

        try:
            response = client.responses.create(**request_data)
        except Exception as error:
            if not should_retry_without_optional_generation_options(error, options):
                raise

            request_data = {
                "model": self.model,
                "input": prompt,
            }
            apply_generation_options(request_data, minimal_generation_options(options))
            response = client.responses.create(**request_data)

        self.last_metadata = ProviderMetadata(
            model=getattr(response, "model", self.model),
            finish_reason=extract_finish_reason(response),
            usage=getattr(response, "usage", None),
        )
        return response.output_text

    def metadata(self):
        """Return metadata compatible with AIIntentParser."""
        return self.last_metadata


class MockProvider:
    """Mock provider that intentionally returns non-JSON text."""

    def __init__(self, model):
        self.last_metadata = ProviderMetadata(model or "mock")

    def generate(self, prompt, **options):
        return "mock provider does not return structured JSON"

    def metadata(self):
        return self.last_metadata


class ProviderMetadata:
    """Small metadata object compatible with AIIntentParser."""

    def __init__(self, model, finish_reason="", usage=None):
        self.model = model
        self.finish_reason = finish_reason
        self.usage = usage


def apply_generation_options(request_data, options):
    """Apply AI Intent Parser generation options to the smoke test API call."""
    max_output_tokens = options.get("max_output_tokens")
    reasoning_effort = str(options.get("reasoning_effort", "") or "")
    verbosity = str(options.get("verbosity", "") or "")

    if max_output_tokens is not None:
        request_data["max_output_tokens"] = int(max_output_tokens)

    if reasoning_effort != "":
        request_data["reasoning"] = {"effort": reasoning_effort}

    if verbosity != "":
        request_data["text"] = {"verbosity": verbosity}


def should_retry_without_optional_generation_options(error, options):
    """Return whether optional intent generation knobs likely caused a 400."""
    if not options:
        return False

    message = str(error).lower()

    if "400" not in message and "bad request" not in message:
        return False

    return any(token in message for token in ["reasoning", "verbosity", "text", "unknown parameter", "unsupported", "invalid"])


def minimal_generation_options(options):
    """Keep only broadly supported generation options for a retry."""
    if "max_output_tokens" not in options:
        return {}

    return {"max_output_tokens": options["max_output_tokens"]}


def extract_finish_reason(response):
    """Extract a best-effort finish reason from Responses API objects."""
    finish_reason = getattr(response, "finish_reason", "")

    if finish_reason:
        return finish_reason

    for output_item in getattr(response, "output", []) or []:
        finish_reason = getattr(output_item, "finish_reason", "") or getattr(output_item, "stop_reason", "")

        if finish_reason:
            return finish_reason

        for content_item in getattr(output_item, "content", []) or []:
            finish_reason = getattr(content_item, "finish_reason", "") or getattr(content_item, "stop_reason", "")

            if finish_reason:
                return finish_reason

    return ""


def read_env_value(name):
    """Read one value from local .env."""
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return ""

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            key, value = parse_env_line(line)
            if key == name:
                return value

    return ""


def parse_env_line(line):
    """Parse simple KEY=VALUE lines."""
    stripped = line.strip()
    if stripped == "" or stripped.startswith("#") or "=" not in stripped:
        return "", ""

    key, value = stripped.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key.strip(), value


if __name__ == "__main__":
    main()
