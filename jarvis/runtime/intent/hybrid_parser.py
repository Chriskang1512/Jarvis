from jarvis.debug_trace import trace_event
from jarvis.runtime.intent.ai_parser import AIIntentParser
from jarvis.runtime.intent.metrics import get_intent_metrics
from jarvis.runtime.intent.models import IntentContext, IntentParseResult
from jarvis.runtime.intent.registry import create_default_intent_registry
from jarvis.runtime.intent.rule_parser import RuleIntentParser
from jarvis.runtime.intent.validator import IntentValidator


class HybridIntentParser:
    """Rule-first parser with optional AI fallback and validation."""

    def __init__(
        self,
        rule_parser=None,
        ai_parser=None,
        validator=None,
        registry=None,
        rule_confidence_threshold=0.90,
        execute_confidence_threshold=0.85,
        min_confidence=0.70,
    ):
        """Create hybrid parser."""
        self.registry = registry or create_default_intent_registry()
        self.rule_parser = rule_parser or RuleIntentParser()
        self.ai_parser = ai_parser or AIIntentParser(enabled=False)
        self.validator = validator or IntentValidator(registry=self.registry)
        self.rule_confidence_threshold = float(rule_confidence_threshold)
        self.execute_confidence_threshold = float(execute_confidence_threshold)
        self.min_confidence = float(min_confidence)

    def parse(self, text: str, context: IntentContext) -> IntentParseResult:
        """Parse with rule first, then AI if needed."""
        rule_result = self.rule_parser.parse(text, context)
        trace_event(
            "intent.rule",
            matched=rule_result.success,
            confidence=rule_result.confidence,
        )

        if rule_result.unsupported_reason:
            selected = self.validator.validate_result(rule_result)
            trace_event("intent.selected", source="rule")
            return record_intent_metrics(selected, "rule")

        if rule_result.success and rule_result.confidence >= self.rule_confidence_threshold:
            selected = self.validator.validate_result(rule_result)
            trace_event("intent.validation", success=selected.success)
            trace_event("intent.selected", source="rule")
            return record_intent_metrics(selected, "rule")

        ai_result = self.ai_parser.parse(text, context)

        if not ai_result.success and not ai_result.requires_clarification and not ai_result.unsupported_reason:
            if rule_result.success:
                selected = self.validator.validate_result(rule_result)
                trace_event("intent.selected", source="rule_fallback")
                return record_intent_metrics(selected, "rule_fallback")

            trace_event("intent.selected", source="fallback")
            return record_intent_metrics(ai_result, "fallback")

        selected = self.validator.validate_result(apply_confidence_policy(ai_result, self.registry, self.execute_confidence_threshold, self.min_confidence))
        trace_event("intent.validation", success=selected.success)
        trace_event("intent.selected", source="ai")
        return record_intent_metrics(selected, "ai")


def apply_confidence_policy(result, registry, execute_threshold, min_confidence):
    """Apply Sprint 8 confidence policy."""
    if result.requires_clarification or result.unsupported_reason:
        return result

    if result.confidence < min_confidence:
        return IntentParseResult(
            success=False,
            source=result.source,
            confidence=result.confidence,
            requires_clarification=True,
            clarification_question="조금 더 구체적으로 말씀해 주세요.",
            raw_text=result.raw_text,
            normalized_text=result.normalized_text,
        )

    has_write = any(is_write_intent(intent, registry) for intent in result.intents)

    if has_write and result.confidence < execute_threshold:
        return IntentParseResult(
            success=False,
            intents=result.intents,
            source=result.source,
            confidence=result.confidence,
            requires_clarification=True,
            clarification_question="이 작업을 실행하려면 조금 더 구체적으로 말씀해 주세요.",
            raw_text=result.raw_text,
            normalized_text=result.normalized_text,
        )

    return result


def is_write_intent(intent, registry):
    """Return whether intent is a mutating action."""
    spec = registry.get(intent.ability, intent.action)
    return bool(getattr(spec, "write", False))


def record_intent_metrics(result, source):
    """Record aggregate Intent routing metrics and return the result."""
    if source != "ai":
        trace_event(
            "intent.metrics",
            latency_ms=getattr(result, "latency_ms", 0),
            input_tokens=getattr(result, "input_tokens", 0),
            output_tokens=getattr(result, "output_tokens", 0),
            intent_count=len(getattr(result, "intents", ()) or ()),
            finish_reason=getattr(result, "finish_reason", ""),
            truncated=getattr(result, "truncated", False),
            source=source,
        )

    metrics = get_intent_metrics()
    metrics.record(
        source=source,
        confidence=getattr(result, "confidence", 0.0),
        requires_clarification=getattr(result, "requires_clarification", False),
    )
    snapshot = metrics.snapshot()
    trace_event(
        "intent.stats",
        total=snapshot.total,
        rule_hit_rate=snapshot.rule_hit_rate,
        ai_hit_rate=snapshot.ai_hit_rate,
        fallback_rate=snapshot.fallback_rate,
        clarification_rate=snapshot.clarification_rate,
        average_confidence=snapshot.average_confidence,
    )
    return result
