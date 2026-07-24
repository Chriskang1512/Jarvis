import json
import os
import re
from time import perf_counter

from jarvis.debug_trace import trace_event
from jarvis.runtime.intent.errors import AI_PARSER_DISABLED, AI_PARSER_FAILED
from jarvis.runtime.intent.models import IntentContext, IntentParseResult, StructuredIntent


class AIIntentParser:
    """LLM-backed parser that returns structured intent JSON only."""

    def __init__(
        self,
        provider=None,
        model="",
        enabled=None,
        timeout_seconds=None,
        min_confidence=None,
        max_output_tokens=None,
        reasoning_effort=None,
        verbosity=None,
    ):
        """Create AI parser with an LLM provider abstraction."""
        self.provider = provider
        self.model = model or read_env("JARVIS_INTENT_MODEL", "")
        self.enabled = read_bool("JARVIS_AI_INTENT_ENABLED", False) if enabled is None else bool(enabled)
        self.timeout_seconds = float(timeout_seconds if timeout_seconds is not None else read_env("JARVIS_AI_INTENT_TIMEOUT", "8") or 8)
        self.min_confidence = float(
            min_confidence if min_confidence is not None else read_env("JARVIS_AI_INTENT_MIN_CONFIDENCE", "0.70") or 0.70
        )
        self.max_output_tokens = int(
            max_output_tokens
            if max_output_tokens is not None
            else read_env("JARVIS_AI_INTENT_MAX_OUTPUT_TOKENS", "300")
            or 300
        )
        self.reasoning_effort = str(
            reasoning_effort if reasoning_effort is not None else read_env("JARVIS_AI_INTENT_REASONING_EFFORT", "low")
        )
        self.verbosity = str(verbosity if verbosity is not None else read_env("JARVIS_AI_INTENT_VERBOSITY", "low"))

    def parse(self, text: str, context: IntentContext) -> IntentParseResult:
        """Parse text by asking the provider for schema-shaped JSON."""
        raw_text = str(text or "").strip()
        normalized = " ".join(raw_text.split())

        if not self.enabled or self.provider is None:
            return IntentParseResult(
                success=False,
                source="ai",
                raw_text=raw_text,
                normalized_text=normalized,
                error_code=AI_PARSER_DISABLED,
                error_message="AI intent parser is disabled or has no provider.",
            )

        started = perf_counter()
        model_name = self.model or provider_model_name(self.provider)
        trace_event("intent.ai.requested", model=model_name)

        try:
            reply = generate_intent_response(
                self.provider,
                create_intent_prompt(normalized, context),
                create_generation_options(self.max_output_tokens, self.reasoning_effort, self.verbosity),
            )
            finish_reason = provider_finish_reason(self.provider)
            if is_truncated_finish_reason(finish_reason):
                raise ValueError("AI intent parser output was truncated.")
            payload = parse_json_payload(reply)
            result = parse_ai_payload(payload, raw_text, normalized, elapsed_ms(started), self.provider)
        except Exception as error:
            usage = provider_usage(self.provider)
            finish_reason = provider_finish_reason(self.provider)
            truncated = is_truncated_finish_reason(finish_reason)
            trace_event(
                "intent.ai.failed",
                latency_ms=elapsed_ms(started),
                error=str(error),
                finish_reason=finish_reason,
            )
            trace_event(
                "intent.metrics",
                latency_ms=elapsed_ms(started),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                intent_count=0,
                finish_reason=finish_reason,
                truncated=truncated,
                source="ai",
            )
            return IntentParseResult(
                success=False,
                source="ai",
                raw_text=raw_text,
                normalized_text=normalized,
                latency_ms=elapsed_ms(started),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                finish_reason=finish_reason,
                truncated=truncated,
                requires_clarification=truncated,
                clarification_question="요청을 안전하게 해석하지 못했습니다. 다시 한 번 말씀해 주세요." if truncated else "",
                error_code=AI_PARSER_FAILED,
                error_message=str(error),
            )

        first = result.first_intent
        trace_event(
            "intent.ai.parsed",
            ability=getattr(first, "ability", ""),
            action=getattr(first, "action", ""),
            confidence=result.confidence,
        )
        trace_event(
            "intent.metrics",
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            intent_count=len(result.intents),
            finish_reason=result.finish_reason,
            truncated=result.truncated,
            source=result.source,
        )
        return result


def create_intent_prompt(text, context):
    """Create a compact JSON-only intent prompt."""
    return json.dumps(
        {
            "task": "Parse the user text into Jarvis intents. Return JSON only. Never execute. Never explain.",
            "text": text,
            "context": {
                "current_date": context.current_date,
                "current_time": context.current_time,
                "timezone": context.timezone,
                "known_people": list((context.user_vocabulary or {}).keys()),
                "pending_action": bool(context.pending_action),
            },
            "allowed": compact_allowed_actions(context),
            "rules": [
                "Use only allowed ability.action values.",
                "Output shape: {intents:[{ability,action,parameters,depends_on,confidence}],confidence,clarification_question,unsupported_reason}.",
                "Use short action names: health, execute, create, list, query, remember, recall, forget, cancel, update, delete.",
                "Missing required details => clarification_question.",
                "Unsupported conditionals => unsupported_reason='conditional_execution'.",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def compact_allowed_actions(context):
    """Return a short allow-list for the AI parser prompt."""
    available_actions = list(context.available_actions or [])

    if available_actions:
        return available_actions

    return [
        "weather.query",
        "memory.remember",
        "memory.recall",
        "memory.forget",
        "memory.list",
        "calendar.create",
        "calendar.list",
        "calendar.update",
        "calendar.delete",
        "contacts.create",
        "contacts.update",
        "contacts.get",
        "contacts.delete",
        "contacts.list",
        "mail.list",
        "mail.search",
        "mail.get",
        "mail.send",
        "mail.reply",
        "todo.create",
        "todo.update",
        "todo.complete",
        "todo.delete",
        "todo.list",
        "todo.restore",
        "reminder.create",
        "reminder.cancel",
        "reminder.list",
        "integration_n8n.health",
        "integration_n8n.execute",
    ]


def create_generation_options(max_output_tokens, reasoning_effort, verbosity):
    """Create provider generation options for compact intent classification."""
    options = {"max_output_tokens": int(max_output_tokens)}

    if str(reasoning_effort or "").strip() != "":
        options["reasoning_effort"] = str(reasoning_effort).strip()

    if str(verbosity or "").strip() != "":
        options["verbosity"] = str(verbosity).strip()

    return options


def generate_intent_response(provider, prompt, options):
    """Generate intent JSON, falling back for test providers without kwargs."""
    try:
        return provider.generate(prompt, **options)
    except TypeError:
        return provider.generate(prompt)


def parse_json_payload(text):
    """Parse provider response as JSON object."""
    value = str(text or "").strip()

    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value).strip()
        value = re.sub(r"```$", "", value).strip()

    if not value.startswith("{"):
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            raise ValueError("AI parser did not return JSON.")
        value = match.group(0)

    payload = json.loads(value)

    if not isinstance(payload, dict):
        raise ValueError("AI parser JSON must be an object.")

    return payload


def parse_ai_payload(payload, raw_text, normalized, latency_ms, provider):
    """Convert provider JSON to IntentParseResult."""
    unsupported_reason = str(payload.get("unsupported_reason", "") or "")
    requires_clarification = bool(payload.get("requires_clarification", False))
    clarification_question = str(payload.get("clarification_question", "") or "")
    raw_intents = payload.get("intents")

    if raw_intents is None:
        raw_intents = [payload]

    if not isinstance(raw_intents, list):
        raise ValueError("AI parser intents must be a list.")

    intents = tuple(parse_one_intent(item, raw_text, normalized) for item in raw_intents if isinstance(item, dict))
    confidence = max([intent.confidence for intent in intents], default=float(payload.get("confidence", 0.0) or 0.0))
    usage = provider_usage(provider)
    finish_reason = provider_finish_reason(provider)
    truncated = is_truncated_finish_reason(finish_reason)

    return IntentParseResult(
        success=len(intents) > 0 and not requires_clarification and unsupported_reason == "" and not truncated,
        intents=intents,
        source="ai",
        confidence=confidence,
        requires_clarification=requires_clarification or truncated,
        clarification_question=clarification_question
        or ("요청을 안전하게 해석하지 못했습니다. 다시 한 번 말씀해 주세요." if truncated else ""),
        unsupported_reason=unsupported_reason,
        raw_text=raw_text,
        normalized_text=normalized,
        latency_ms=latency_ms,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        finish_reason=finish_reason,
        truncated=truncated,
    )


def parse_one_intent(data, raw_text, normalized):
    """Convert one JSON object to StructuredIntent."""
    intent_id = str(data.get("intent_id", ""))
    ability = str(data.get("ability", ""))
    action = normalize_action(str(data.get("action", "")), intent_id)
    return StructuredIntent(
        intent_id=intent_id,
        ability=ability,
        action=action,
        entities=dict(data.get("entities", {}) or {}),
        parameters=dict(data.get("parameters", {}) or {}),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        requires_clarification=bool(data.get("requires_clarification", False)),
        clarification_question=str(data.get("clarification_question", "") or ""),
        source="ai",
        raw_text=raw_text,
        normalized_text=normalized,
        depends_on=data.get("depends_on"),
        unsupported_reason=str(data.get("unsupported_reason", "") or ""),
    )


def normalize_action(action, intent_id):
    """Normalize common AI mistakes such as action=integration.health."""
    action = str(action or "").strip()
    intent_id = str(intent_id or "").strip()

    if "." in action:
        return action.rsplit(".", 1)[-1]

    if action == "" and "." in intent_id:
        return intent_id.rsplit(".", 1)[-1]

    return action


def provider_usage(provider):
    """Return token usage from provider metadata when available."""
    metadata = getattr(provider, "last_metadata", None)
    usage = getattr(metadata, "usage", None)

    return {
        "input_tokens": int(getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0),
    }


def provider_finish_reason(provider):
    """Return the latest provider finish reason when available."""
    metadata = getattr(provider, "last_metadata", None)
    return str(getattr(metadata, "finish_reason", "") or "")


def is_truncated_finish_reason(finish_reason):
    """Return whether the provider reports a token limit stop."""
    return str(finish_reason or "").lower() in ["length", "max_tokens", "max_output_tokens"]


def provider_model_name(provider):
    """Return provider model name for traces."""
    try:
        metadata = provider.metadata()
    except Exception:
        return ""

    return getattr(metadata, "model", "")


def read_bool(key, default):
    """Read boolean env value."""
    value = read_env(key, "")

    if value == "":
        return default

    return value.lower() in ["1", "true", "yes", "on"]


def read_env(key, default):
    """Read env value."""
    return os.environ.get(key, default)


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)
