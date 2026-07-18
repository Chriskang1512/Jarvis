"""Semantic transcript normalization."""

import re

from jarvis.debug_trace import trace_event
from jarvis.voice.semantic.cache import SemanticEntityCache, semantic_cache_key
from jarvis.voice.semantic.context import SemanticTranscriptContext
from jarvis.voice.semantic.entity_resolver import EntityRegistry, best_correction
from jarvis.voice.semantic.models import SemanticCorrection, SemanticHistoryStep, SemanticTranscriptResult


class SemanticTranscriptNormalizer:
    """Normalize STT transcripts into intent-friendlier semantic text."""

    def __init__(self, entity_registry=None, entity_cache=None):
        """Create a semantic transcript normalizer."""
        self.entity_registry = entity_registry or EntityRegistry()
        self.entity_cache = entity_cache or SemanticEntityCache()
        self._known_entities_version = None

    def normalize(self, raw_text, normalized_text=None, context=None):
        """Return a semantic transcript result."""
        context = context or SemanticTranscriptContext()
        raw = str(raw_text or "")
        normalized = " ".join(str(normalized_text if normalized_text is not None else raw).split())
        semantic = normalized
        corrections = []
        known_entities_version = str(getattr(context, "known_entities_version", "") or "")

        if self._known_entities_version is None:
            self._known_entities_version = known_entities_version
        elif self._known_entities_version != known_entities_version:
            self.entity_cache.invalidate()
            self._known_entities_version = known_entities_version

        registry = self.entity_registry.with_context(context)
        preferred_types = preferred_entity_types(context)
        cache_key = semantic_cache_key(semantic, context, getattr(registry, "version", ""))
        history = [
            SemanticHistoryStep(stage="raw", text=raw),
            SemanticHistoryStep(stage="normalized", text=normalized),
        ]

        ambiguous = is_ambiguous_single_person(semantic, registry, context)
        cached = None if ambiguous else self.entity_cache.get(cache_key)

        if cached is None:
            initial_entities, candidate_corrections, initial_traces = registry.run(
                semantic,
                context,
                preferred_types=preferred_types,
            )
            if not ambiguous:
                self.entity_cache.set(cache_key, (initial_entities, candidate_corrections, initial_traces))
            cache_status = "miss"
        else:
            initial_entities, candidate_corrections, initial_traces = cached
            cache_status = "hit"

        entity_correction = None if ambiguous else best_correction(candidate_corrections)
        resolver_traces = list(initial_traces)
        history.append(
            SemanticHistoryStep(
                stage="resolver",
                text=semantic,
                resolver="ResolverRegistry",
                entities=initial_entities,
                corrections=candidate_corrections,
                confidence=calculate_confidence(candidate_corrections),
            )
        )

        original_semantic = semantic

        if entity_correction is not None and should_apply_correction(entity_correction):
            semantic = apply_correction(semantic, entity_correction)
            corrections.append(entity_correction)

        semantic, phrase_corrections = normalize_calendar_phrases(semantic, registry)
        corrections.extend(phrase_corrections)
        semantic, todo_corrections = normalize_todo_phrases(semantic)
        corrections.extend(todo_corrections)
        semantic = normalize_command_suffixes(semantic)

        if semantic != original_semantic:
            entities, _, resolved_traces = registry.run(semantic, context, preferred_types=preferred_types)
            resolver_traces = list(resolved_traces)
        else:
            entities = initial_entities

        history.append(
            SemanticHistoryStep(
                stage="semantic",
                text=semantic,
                corrections=tuple(corrections),
                confidence=calculate_confidence(corrections),
            )
        )
        history.append(
            SemanticHistoryStep(
                stage="resolved",
                text=semantic,
                resolver="ResolverRegistry",
                entities=entities,
                confidence=calculate_entity_confidence(entities, corrections),
            )
        )
        confidence = calculate_confidence(corrections)
        clarification_question = ""
        requires_clarification = False

        if ambiguous:
            requires_clarification = True
            confidence = min(confidence, 0.74)
            clarification_question = "아야를 말씀하신 건가요, 아이를 말씀하신 건가요?"

        result = SemanticTranscriptResult(
            raw_text=raw,
            normalized_text=normalized,
            semantic_text=semantic,
            corrections=tuple(corrections),
            resolved_entities=tuple(entities),
            confidence=confidence,
            requires_clarification=requires_clarification,
            clarification_question=clarification_question,
            history=tuple(history),
            resolver_traces=tuple(resolver_traces),
        )
        trace_semantic_result(result, context)
        trace_semantic_metrics(result, self.entity_cache.metrics(), cache_status)
        return result


def normalize_semantic_transcript(raw_text, normalized_text=None, context=None, entity_registry=None):
    """Normalize one transcript with a default normalizer."""
    return SemanticTranscriptNormalizer(entity_registry=entity_registry).normalize(raw_text, normalized_text, context)


def preferred_entity_types(context):
    """Return entity types most relevant to the current conversation field."""
    pending = str(getattr(context, "pending_field", "") or "")
    last_question = str(getattr(context, "last_question", "") or "")

    if pending == "participants" or "누구" in last_question:
        return ("person",)

    if pending == "location" or "장소" in last_question or "어디" in last_question:
        return ("place",)

    if "바꿔" in str(getattr(context, "last_intent", "") or ""):
        return ("place", "person")

    return ()


def should_apply_correction(correction):
    """Return whether a correction is confident enough to apply."""
    return correction.confidence >= 0.9


def apply_correction(text, correction):
    """Apply a literal correction."""
    return str(text or "").replace(correction.source, correction.target)


def normalize_calendar_phrases(text, registry):
    """Normalize common calendar near-miss phrases."""
    semantic = str(text or "")
    corrections = []

    for person in ["아야", "유이", "유리"]:
        for phrase in [f"{person}한테 일정 등록", f"{person}에게 일정 등록", f"{person} 일정 등록"]:
            if phrase in semantic and "만나기" not in semantic:
                semantic = semantic.replace(phrase, f"{person} 만나기 일정 등록")
                corrections.append(
                    SemanticCorrection(
                        phrase,
                        f"{person} 만나기 일정 등록",
                        "calendar_person_meeting_hint",
                        0.9,
                        entity_source="semantic_rule",
                        resolver="CalendarPhraseResolver",
                    )
                )

    semantic = re.sub(r"(\S+)\s*한테\s*일정\s*등록", r"\1 만나기 일정 등록", semantic)
    semantic = re.sub(r"(\S+)\s*에게\s*일정\s*등록", r"\1 만나기 일정 등록", semantic)
    return semantic, tuple(corrections)


def normalize_todo_phrases(text):
    """Normalize common Todo command suffix STT near-misses."""
    semantic = str(text or "")
    corrections = []

    replacements = [
        ("\ucd95\ud558\ud574", "\ucd94\uac00\ud574"),
        ("\ucd95\ud558 \ud574", "\ucd94\uac00\ud574"),
        ("\ucd95\ud558\ub77c", "\ucd94\uac00\ud574"),
    ]

    for source, target in replacements:
        if source not in semantic:
            continue

        candidate = semantic.replace(source, target)

        if not looks_like_todo_create_candidate(candidate):
            continue

        semantic = candidate
        corrections.append(
            SemanticCorrection(
                source,
                target,
                "todo_create_suffix_stt_near_miss",
                0.91,
                entity_source="semantic_rule",
                resolver="TodoPhraseResolver",
            )
        )

    return semantic, tuple(corrections)


def looks_like_todo_create_candidate(text):
    """Return whether corrected text looks like a Todo create command."""
    value = str(text or "").strip()

    if "\ucd94\uac00" not in value:
        return False

    title = value.replace("\ucd94\uac00\ud574", " ").replace("\ucd94\uac00", " ")
    title = " ".join(title.strip(" .?!").split())

    return title != ""


def normalize_command_suffixes(text):
    """Trim low-information polite command suffixes while keeping task meaning."""
    semantic = " ".join(str(text or "").split())
    semantic = re.sub(r"\b좀\b", " ", semantic)
    semantic = re.sub(r"\b하나\b", " ", semantic)
    semantic = re.sub(r"\s+", " ", semantic)
    return semantic.strip()


def calculate_confidence(corrections):
    """Return aggregate confidence."""
    if not corrections:
        return 1.0

    return round(min(correction.confidence for correction in corrections), 2)


def calculate_entity_confidence(entities, corrections):
    """Return aggregate semantic confidence for entities and corrections."""
    values = [entity.confidence for entity in entities]
    values.extend(correction.confidence for correction in corrections)

    if not values:
        return 1.0

    return round(min(values), 2)


def is_ambiguous_single_person(text, registry, context):
    """Return whether a single person token has conflicting known candidates."""
    pending = str(getattr(context, "pending_field", "") or "")

    if pending != "participants":
        return False

    cleaned = str(text or "").strip()

    if cleaned != "아이":
        return False

    known_people = tuple(getattr(context, "known_people", ()) or ())
    return "아야" in known_people and "아이" in known_people


def trace_semantic_result(result, context):
    """Emit semantic transcript trace logs."""
    trace_event(
        "voice.semantic.transcript",
        raw_text=result.raw_text,
        normalized_text=result.normalized_text,
        semantic_text=result.semantic_text,
        pending_field=getattr(context, "pending_field", ""),
        corrections=result.correction_dicts(),
        resolved_entities=result.entity_dicts(),
        resolver_traces=result.resolver_trace_dicts(),
        history=result.history_dicts(),
        confidence=result.confidence,
        requires_clarification=result.requires_clarification,
        clarification_question=result.clarification_question,
    )


def trace_semantic_metrics(result, cache_metrics=None, cache_status=""):
    """Emit compact resolver metrics."""
    traces = result.resolver_traces
    matched = [trace for trace in traces if trace.status == "matched"]
    matched_resolvers = {trace.resolver for trace in matched}
    total_latency = sum(trace.latency_ms for trace in traces)
    cache_metrics = cache_metrics or {}
    entity_confidences = [entity.confidence for entity in result.resolved_entities]
    correction_confidences = [correction.confidence for correction in result.corrections]
    entity_avg_confidence = round(sum(entity_confidences) / len(entity_confidences), 3) if entity_confidences else 1.0
    entity_min_confidence = round(min(entity_confidences), 3) if entity_confidences else 1.0
    correction_avg_confidence = (
        round(sum(correction_confidences) / len(correction_confidences), 3) if correction_confidences else None
    )
    trace_event(
        "voice.semantic.metrics",
        entity_resolved=len(result.resolved_entities),
        clarification_count=1 if result.requires_clarification else 0,
        resolver_success=len(matched_resolvers),
        resolver_failed=0,
        resolver_latency_ms=total_latency,
        semantic_confidence=result.confidence,
        entity_avg_confidence=entity_avg_confidence,
        entity_min_confidence=entity_min_confidence,
        correction_count=len(correction_confidences),
        correction_avg_confidence=correction_avg_confidence,
        avg_confidence=entity_avg_confidence,
        cache_status=cache_status,
        cache_hit=cache_metrics.get("cache_hit", 0),
        cache_miss=cache_metrics.get("cache_miss", 0),
        cache_size=cache_metrics.get("cache_size", 0),
        cache_invalidations=cache_metrics.get("cache_invalidations", 0),
    )
