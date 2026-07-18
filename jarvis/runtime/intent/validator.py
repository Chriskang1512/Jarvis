import re
from datetime import date, datetime

from jarvis.runtime.intent.errors import (
    CONDITIONAL_EXECUTION_UNSUPPORTED,
    FORBIDDEN_PROVIDER_OR_URL,
    INVALID_ACTION_FOR_ABILITY,
    INVALID_DATE_TIME,
    MISSING_REQUIRED_PARAMETER,
)
from jarvis.runtime.intent.models import IntentParseResult, StructuredIntent
from jarvis.runtime.intent.registry import create_default_intent_registry


URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)


class IntentValidator:
    """Validate structured intents before planning or dispatch."""

    def __init__(self, registry=None):
        """Create validator with a known intent registry."""
        self.registry = registry or create_default_intent_registry()

    def validate_result(self, result):
        """Validate every intent in a parser result."""
        if result.unsupported_reason == "conditional_execution":
            return IntentParseResult(
                success=False,
                source=result.source,
                raw_text=result.raw_text,
                normalized_text=result.normalized_text,
                unsupported_reason="conditional_execution",
                error_code=CONDITIONAL_EXECUTION_UNSUPPORTED,
                error_message="Conditional execution is not supported yet.",
            )

        if result.requires_clarification:
            return result

        validated = []

        for intent in result.intents:
            error_code, error_message = self.validate_intent(intent)

            if error_code:
                return IntentParseResult(
                    success=False,
                    source=result.source,
                    raw_text=result.raw_text,
                    normalized_text=result.normalized_text,
                    error_code=error_code,
                    error_message=error_message,
                )

            validated.append(intent)

        return IntentParseResult(
            success=len(validated) > 0,
            intents=tuple(validated),
            source=result.source,
            confidence=result.confidence,
            raw_text=result.raw_text,
            normalized_text=result.normalized_text,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    def validate_intent(self, intent):
        """Return error code/message for one invalid intent, else empty pair."""
        spec = self.registry.get(intent.ability, intent.action)

        if spec is None:
            ability_known = intent.ability in self.registry.list_abilities()
            if ability_known:
                return INVALID_ACTION_FOR_ABILITY, f"Action '{intent.action}' is not allowed for '{intent.ability}'."
            return INVALID_ACTION_FOR_ABILITY, f"Ability '{intent.ability}' is not registered for intent parsing."

        data = merged_parameters(intent)

        for key in spec.required_parameters:
            if str(data.get(key, "")).strip() == "":
                return MISSING_REQUIRED_PARAMETER, f"Missing required parameter: {key}"

        date_error = validate_dates(data)

        if date_error:
            return INVALID_DATE_TIME, date_error

        semantic_error, semantic_message = validate_semantic_safety(intent, data)

        if semantic_error:
            return semantic_error, semantic_message

        if contains_forbidden_url(data):
            return FORBIDDEN_PROVIDER_OR_URL, "AI intent output must not include URLs or provider endpoints."

        return "", ""


def merged_parameters(intent):
    """Return entities and parameters in one dictionary."""
    data = {}
    data.update(dict(intent.entities))
    data.update(dict(intent.parameters))
    return data


def validate_dates(data):
    """Return date/time validation message or empty string."""
    date_value = str(data.get("date", "") or "")
    datetime_value = str(data.get("datetime", "") or "")
    time_value = str(data.get("time", "") or "")

    if date_value:
        try:
            date.fromisoformat(date_value)
        except ValueError:
            return f"Invalid date: {date_value}"

    if datetime_value:
        try:
            datetime.fromisoformat(datetime_value)
        except ValueError:
            return f"Invalid datetime: {datetime_value}"

    if time_value and not re.match(r"^\d{2}:\d{2}(:\d{2})?$", time_value):
        return f"Invalid time: {time_value}"

    return ""


def validate_semantic_safety(intent, data):
    """Return an error when an AI write intent is not grounded in the transcript."""
    if intent.ability == "todo" and intent.action == "create":
        source_text = " ".join(
            str(value or "")
            for value in [
                intent.raw_text,
                intent.normalized_text,
                data.get("raw_text", ""),
            ]
        )

        if source_text.strip() and not has_todo_create_signal(source_text):
            return MISSING_REQUIRED_PARAMETER, "Missing explicit Todo create signal in transcript."

    if intent.ability == "reminder" and intent.action == "create":
        if not has_reminder_time_signal(intent, data):
            return MISSING_REQUIRED_PARAMETER, "Missing explicit reminder time."

    return "", ""


def has_todo_create_signal(text):
    """Return whether text explicitly asks to create a Todo."""
    normalized = str(text or "")
    return any(
        token in normalized
        for token in [
            "추가",
            "등록",
            "저장",
            "넣어",
            "해야 할 일",
            "할 일로",
            "할일로",
            "todo",
            "to-do",
        ]
    )


def has_reminder_time_signal(intent, data):
    """Return whether reminder.create has a real time expression."""
    if str(data.get("datetime", "") or "").strip():
        return True

    if str(data.get("relative_minutes", "") or "").strip():
        return True

    if str(data.get("relative_seconds", "") or "").strip():
        return True

    if intent.depends_on is not None and str(data.get("remind_before_minutes", "") or "").strip():
        return True

    text = " ".join(str(value or "") for value in [data.get("raw_text", ""), data.get("title", "")])
    return bool(re.search(r"\d+\s*(분|시간|초)\s*(뒤|후|있다가|전)", text))


def contains_forbidden_url(value):
    """Return whether nested data contains a URL."""
    if isinstance(value, str):
        return URL_PATTERN.search(value) is not None

    if isinstance(value, dict):
        return any(contains_forbidden_url(item) for item in value.values())

    if isinstance(value, (list, tuple)):
        return any(contains_forbidden_url(item) for item in value)

    return False


def validate_intent_result(result, registry=None):
    """Convenience validation helper."""
    return IntentValidator(registry=registry).validate_result(result)
