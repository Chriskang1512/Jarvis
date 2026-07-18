from datetime import date, timedelta

from jarvis.runtime.intent.models import IntentContext, IntentParseResult, StructuredIntent


class RuleIntentParser:
    """Small high-confidence rule parser for predictable commands."""

    def parse(self, text: str, context: IntentContext) -> IntentParseResult:
        """Parse high-confidence known commands."""
        raw_text = str(text or "").strip()
        normalized = " ".join(raw_text.split())

        if normalized == "":
            return empty_rule_result(raw_text, normalized)

        intent = parse_rule_intent(normalized, context)

        if intent is None:
            return IntentParseResult(
                success=False,
                source="rule",
                confidence=0.0,
                raw_text=raw_text,
                normalized_text=normalized,
            )

        if intent.unsupported_reason:
            return IntentParseResult(
                success=False,
                intents=(intent,),
                source="rule",
                confidence=intent.confidence,
                raw_text=raw_text,
                normalized_text=normalized,
                unsupported_reason=intent.unsupported_reason,
            )

        return IntentParseResult(
            success=True,
            intents=(intent,),
            source="rule",
            confidence=intent.confidence,
            raw_text=raw_text,
            normalized_text=normalized,
        )


def parse_rule_intent(text, context):
    """Return one rule intent or None."""
    if "조건" in text or ("비" in text and "오면" in text):
        return StructuredIntent(
            intent_id="unsupported.conditional",
            ability="",
            action="",
            confidence=0.95,
            source="rule",
            raw_text=text,
            normalized_text=text,
            unsupported_reason="conditional_execution",
        )

    if "날씨" in text:
        return StructuredIntent(
            intent_id="weather.query",
            ability="weather",
            action="query",
            parameters={"text": text},
            confidence=0.95,
            source="rule",
            raw_text=text,
            normalized_text=text,
        )

    if is_integration_health_rule(text):
        return StructuredIntent(
            intent_id="integration.health",
            ability="integration_n8n",
            action="health",
            entities={"workflow_key": "system.health"},
            confidence=0.95,
            source="rule",
            raw_text=text,
            normalized_text=text,
        )

    if is_calendar_list_rule(text):
        return StructuredIntent(
            intent_id="calendar.list",
            ability="calendar",
            action="list",
            parameters={"action": "list", "date": detect_relative_date(text, context), "raw_text": text},
            confidence=0.95,
            source="rule",
            raw_text=text,
            normalized_text=text,
        )

    if is_memory_recall_rule(text):
        return StructuredIntent(
            intent_id="memory.recall",
            ability="memory",
            action="recall",
            parameters={"text": text},
            confidence=0.9,
            source="rule",
            raw_text=text,
            normalized_text=text,
        )

    if is_relative_reminder_rule(text):
        return StructuredIntent(
            intent_id="reminder.create",
            ability="reminder",
            action="create",
            parameters={"text": text},
            confidence=0.95,
            source="rule",
            raw_text=text,
            normalized_text=text,
        )

    return None


def is_integration_health_rule(text):
    """Return whether text is a direct health command."""
    return ("연동" in text or "외부 자동화" in text or "n8n" in text) and ("상태" in text or "연결" in text or "확인" in text)


def is_calendar_list_rule(text):
    """Return whether text asks for schedule listing."""
    return "일정" in text and any(token in text for token in ["알려", "보여", "조회", "뭐"])


def is_memory_recall_rule(text):
    """Return whether text asks known memory recall."""
    return "아야" in text and "생일" in text and any(token in text for token in ["언제", "알려", "기억"])


def is_relative_reminder_rule(text):
    """Return whether text is a direct relative reminder."""
    return any(token in text for token in ["분 뒤", "분뒤", "잠시 후", "있다가"]) and any(
        token in text for token in ["알려", "해줘", "잊지"]
    )


def detect_relative_date(text, context):
    """Return ISO date from today/tomorrow phrases."""
    current_date = context.current_date or date.today().isoformat()
    base = date.fromisoformat(current_date)

    if "모레" in text:
        return (base + timedelta(days=2)).isoformat()

    if "내일" in text:
        return (base + timedelta(days=1)).isoformat()

    return base.isoformat()


def empty_rule_result(raw_text, normalized):
    """Return empty parser result."""
    return IntentParseResult(
        success=False,
        source="rule",
        confidence=0.0,
        raw_text=raw_text,
        normalized_text=normalized,
    )
