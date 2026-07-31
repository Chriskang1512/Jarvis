"""Normalize natural language and existing intent output into goals."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from jarvis.goals.context_engine import ConversationContextEngine
from jarvis.goals.models import (
    EntityReference,
    GoalConstraint,
    GoalSpecification,
    LanguageContext,
    Provenance,
    ProvenanceSource,
    SemanticContext,
    SemanticSlot,
    SuccessCriterion,
    TemporalContext,
)
from jarvis.runtime.intent import HybridIntentParser, IntentContext
from jarvis.runtime.date_resolver import DateResolver
from jarvis.runtime.follow_up import (
    DEFAULT_FOLLOW_UP_PHRASE_REGISTRY,
)


@dataclass(frozen=True)
class GoalParseResult:
    goal: GoalSpecification
    route: str
    parser_source: str
    routing_reasons: tuple[str, ...] = ()
    requires_clarification: bool = False
    clarification_question: str = ""


class GoalParser:
    """Goal parser layered on the existing rule/AI intent parser."""

    def __init__(self, intent_parser=None, context_engine=None, clock=None):
        self.intent_parser = intent_parser or HybridIntentParser()
        self.context_engine = context_engine or ConversationContextEngine()
        self.clock = clock or datetime.now

    def parse(
        self,
        text: str,
        *,
        session_id: str = "default",
        intent_context: IntentContext | None = None,
        user_preferences: dict | None = None,
        system_defaults: dict | None = None,
        explicit_control: dict | None = None,
        user_id: str = "local",
        conversation_id: str = "default",
        turn_id: str = "",
    ) -> GoalParseResult:
        original = str(text or "").strip()
        now = self.clock()
        intent_context = intent_context or IntentContext(
            session_id=session_id,
            current_date=now.date().isoformat(),
            current_time=now.time().isoformat(timespec="seconds"),
        )
        try:
            parsed = self.intent_parser.parse(original, intent_context)
        except Exception:
            parsed = None

        current = build_semantic_context(original, parsed, intent_context)
        previous_reference = contains_previous_reference(original)
        explicit = extract_explicit_slots(original, intent_context)
        merged = self.context_engine.merge(
            session_id,
            current,
            explicit_input=explicit,
            explicit_control=explicit_control,
            user_preferences=user_preferences,
            system_defaults=system_defaults,
            references_previous_result=previous_reference,
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
        intents = tuple(getattr(parsed, "intents", ()) or ())
        routing_reasons = assess_goal_routing(
            original,
            intents,
            has_previous_result=merged.previous_result is not None,
        )
        is_goal = bool(routing_reasons)
        constraints = build_constraints(original)
        criteria = build_success_criteria(original, intents, merged.domain)
        parser_source = getattr(parsed, "source", "") or "semantic_fallback"
        confidence = max(float(getattr(parsed, "confidence", 0.0) or 0.0), merged.confidence)
        if confidence == 0:
            confidence = 0.65
        goal = GoalSpecification(
            goal_id=f"goal-{uuid.uuid4()}",
            original_input=original,
            objective=normalize_objective(original),
            constraints=constraints,
            success_criteria=criteria,
            context=merged,
            confidence=min(confidence, 1.0),
        )
        return GoalParseResult(
            goal=goal,
            route="goal_oriented" if is_goal else "direct",
            parser_source=parser_source,
            routing_reasons=routing_reasons,
            requires_clarification=bool(getattr(parsed, "requires_clarification", False)),
            clarification_question=str(
                getattr(parsed, "clarification_question", "") or ""
            ),
        )


def build_semantic_context(text, parsed, intent_context):
    intents = tuple(getattr(parsed, "intents", ()) or ())
    first = intents[0] if intents else None
    domain = str(getattr(first, "ability", "") or detect_domain(text))
    slots: dict[str, SemanticSlot] = {}
    entities: list[EntityReference] = []
    follow_up = DEFAULT_FOLLOW_UP_PHRASE_REGISTRY.match(text)
    if follow_up.is_follow_up:
        for name, value in {
            "is_follow_up": True,
            "follow_up_language": follow_up.language,
            "follow_up_phrase": (
                follow_up.discourse_marker
                or follow_up.temporal_reference
            ),
        }.items():
            slots[name] = SemanticSlot(
                name=name,
                value=value,
                value_type=type(value).__name__,
                confidence=1.0,
                provenance=Provenance(
                    ProvenanceSource.EXPLICIT_INPUT,
                    detail="follow_up_phrase_registry",
                    parser_id="follow_up_phrase_registry",
                    source_field=name,
                ),
            )
    for intent in intents:
        for name, value in {
            **dict(getattr(intent, "parameters", {}) or {}),
            **dict(getattr(intent, "entities", {}) or {}),
        }.items():
            if name in {"text", "raw_text"}:
                continue
            slots[name] = SemanticSlot(
                name=name,
                value=value,
                value_type=type(value).__name__,
                confidence=float(getattr(intent, "confidence", 0.8) or 0.8),
                provenance=Provenance(
                    ProvenanceSource.CURRENT_TURN_ENTITY,
                    detail=f"{getattr(intent, 'source', 'intent')} intent",
                    parser_id=str(getattr(intent, "source", "intent")),
                    source_field=name,
                ),
            )
            if name in {"person", "contact", "event", "event_id", "location"}:
                entities.append(
                    EntityReference(
                        entity_type=name,
                        value=value,
                        mention=str(value),
                        confidence=float(getattr(intent, "confidence", 0.8) or 0.8),
                    )
                )
    temporal = parse_temporal(text, intent_context)
    return SemanticContext(
        domain=domain,
        slots=slots,
        entities=tuple(entities),
        temporal=temporal,
        language=detect_language(text),
        confidence=float(getattr(parsed, "confidence", 0.0) or 0.0),
    )


def extract_explicit_slots(text, context):
    result = {}
    temporal = parse_temporal(text, context)
    if temporal.date:
        result["date"] = temporal.date
    if temporal.time:
        result["time"] = temporal.time
    if temporal.duration:
        result["duration"] = temporal.duration
    location = extract_location(text)
    if location:
        result["location"] = location
    event_id = re.search(r"\b(?:event|일정)[-_ ]?id[:= ]+([\w-]+)", text, re.I)
    if event_id:
        result["event_id"] = event_id.group(1)
    return result


def parse_temporal(text, context):
    base = date.fromisoformat(context.current_date) if context.current_date else date.today()
    target = ""
    expression = ""
    resolved = DateResolver().resolve(text, reference_date=base)
    if resolved is not None:
        target = resolved.start_date
        expression = resolved.source_text
    if "모레" in text:
        target, expression = (base + timedelta(days=2)).isoformat(), "모레"
    elif "내일" in text:
        target, expression = (base + timedelta(days=1)).isoformat(), "내일"
    elif "오늘" in text:
        target, expression = base.isoformat(), "오늘"
    time_value = ""
    match = re.search(r"(오전|오후)?\s*(\d{1,2})시(?:\s*(\d{1,2})분)?", text)
    if match:
        hour = int(match.group(2))
        if match.group(1) == "오후" and hour < 12:
            hour += 12
        if match.group(1) == "오전" and hour == 12:
            hour = 0
        time_value = f"{hour:02d}:{int(match.group(3) or 0):02d}:00"
    duration = ""
    duration_match = re.search(r"(\d+|한)\s*시간", text)
    if duration_match:
        hours = 1 if duration_match.group(1) == "한" else int(duration_match.group(1))
        duration = f"PT{hours}H"
    return TemporalContext(
        timezone=context.timezone,
        reference_date=base.isoformat(),
        date=target,
        time=time_value,
        duration=duration,
        expression=expression,
    )


def extract_location(text):
    match = re.search(
        r"(서울|강릉|부산|대구|대전|인천|제주|광주|울산|수원|잠실|오사카|도쿄)\s*(?:의)?\s*(?:날씨|에서|일정|비)",
        text,
    )
    return match.group(1) if match else ""


def detect_domain(text):
    for domain, terms in (
        ("weather", ("날씨", "비", "기온")),
        ("calendar", ("일정", "약속", "스케줄")),
        ("contacts", ("연락처", "이메일 주소")),
        ("mail", ("메일", "이메일")),
        ("reminder", ("알려줘", "알림", "리마인드")),
    ):
        if any(term in text for term in terms):
            return domain
    return "general"


def detect_language(text):
    if re.search(r"[가-힣]", text):
        return LanguageContext("ko", "ko-KR", "ko")
    if re.search(r"[\u3040-\u30ff]", text):
        return LanguageContext("ja", "ja-JP", "ja")
    return LanguageContext("en", "en-US", "en")


def contains_previous_reference(text):
    return any(token in text for token in ("아까", "방금", "그 일정", "그 파일", "그 보고서"))


def assess_goal_routing(text, intents, *, has_previous_result=False):
    """Return semantic reasons that require planning instead of keyword voting."""
    reasons: list[str] = []
    capabilities = {
        str(getattr(intent, "ability", "") or "")
        for intent in intents
        if getattr(intent, "ability", "")
    }
    capabilities.update(detect_mentioned_capabilities(text))
    if len(capabilities) >= 2:
        reasons.append("multiple_capabilities")

    if any(getattr(intent, "depends_on", None) is not None for intent in intents):
        reasons.append("result_dependency")
    elif len(capabilities) >= 2 and any(
        token in text for token in ("보고", "찾아서", "확인해서", "한 뒤", "결과로")
    ):
        reasons.append("result_dependency")

    if any(token in text for token in ("하면", "오면", "때만", "경우", "아니면")):
        reasons.append("conditional_branch")

    if any(is_mutating_intent(intent) for intent in intents) or contains_mutation(text):
        reasons.append("external_state_change")

    if has_previous_result:
        reasons.append("previous_result_dependency")

    if any(token in text for token in ("기다렸다", "나중에", "승인 후", "재개")):
        reasons.append("pause_or_resume")

    return tuple(dict.fromkeys(reasons))


def detect_mentioned_capabilities(text):
    found = set()
    for capability, terms in (
        ("weather", ("날씨", "비", "기온")),
        ("calendar", ("일정", "약속", "스케줄")),
        ("contacts", ("연락처", "이메일 주소")),
        ("mail", ("메일 보내", "이메일 보내", "메일로 알려")),
        ("reminder", ("알림", "리마인드", "챙기라고")),
    ):
        if any(term in text for term in terms):
            found.add(capability)
    return found


def is_mutating_intent(intent):
    return str(getattr(intent, "action", "") or "") in {
        "create",
        "update",
        "delete",
        "send",
        "reply",
        "move",
        "cancel",
        "complete",
        "restore",
    }


def contains_mutation(text):
    return any(
        token in text
        for token in (
            "등록해",
            "변경해",
            "바꿔",
            "늦춰",
            "삭제해",
            "보내줘",
            "이동해",
            "취소해",
            "만들어",
        )
    )


def normalize_objective(text):
    return " ".join(text.split())


def build_constraints(text):
    result = []
    if any(token in text for token in ("하면", "오면", "때만", "경우")):
        result.append(GoalConstraint("명시된 조건이 충족될 때만 후속 작업을 실행한다", "condition"))
    if contains_mutation(text) or any(
        token in text for token in ("메일", "일정 등록", "일정 변경", "늦추")
    ):
        result.append(GoalConstraint("외부 변경 또는 메시지 발송 전 사용자 확인", "permission"))
    return tuple(result)


def build_success_criteria(text, intents, domain):
    if intents:
        return tuple(
            SuccessCriterion(
                f"{intent.ability}.{intent.action} 결과가 확인됨"
            )
            for intent in intents
        )
    return (SuccessCriterion(f"{domain} 요청 결과가 확인됨"),)
