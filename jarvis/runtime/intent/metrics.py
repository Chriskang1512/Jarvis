from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class IntentMetricsSnapshot:
    """Point-in-time aggregate metrics for the Intent layer."""

    total: int = 0
    rule_hits: int = 0
    ai_hits: int = 0
    fallback_hits: int = 0
    clarification_hits: int = 0
    confidence_sum: float = 0.0

    @property
    def average_confidence(self):
        """Return average confidence across recorded parses."""
        if self.total <= 0:
            return 0.0
        return self.confidence_sum / self.total

    @property
    def rule_hit_rate(self):
        """Return rule hit percentage."""
        return percentage(self.rule_hits, self.total)

    @property
    def ai_hit_rate(self):
        """Return AI hit percentage."""
        return percentage(self.ai_hits, self.total)

    @property
    def fallback_rate(self):
        """Return fallback percentage."""
        return percentage(self.fallback_hits, self.total)

    @property
    def clarification_rate(self):
        """Return clarification percentage."""
        return percentage(self.clarification_hits, self.total)

    def to_dict(self):
        """Return a serializable metrics dictionary."""
        return {
            "total": self.total,
            "rule_hits": self.rule_hits,
            "ai_hits": self.ai_hits,
            "fallback_hits": self.fallback_hits,
            "clarification_hits": self.clarification_hits,
            "rule_hit_rate": self.rule_hit_rate,
            "ai_hit_rate": self.ai_hit_rate,
            "fallback_rate": self.fallback_rate,
            "clarification_rate": self.clarification_rate,
            "average_confidence": round(self.average_confidence, 4),
        }


class IntentMetricsCollector:
    """In-memory aggregate counters for Intent Parser routing behavior."""

    def __init__(self):
        self._lock = Lock()
        self.reset()

    def reset(self):
        """Clear all counters."""
        with getattr(self, "_lock", Lock()):
            self._total = 0
            self._rule_hits = 0
            self._ai_hits = 0
            self._fallback_hits = 0
            self._clarification_hits = 0
            self._confidence_sum = 0.0

    def record(self, source, confidence=0.0, requires_clarification=False):
        """Record one final parser selection."""
        source = (source or "fallback").lower()
        confidence = safe_float(confidence)

        with self._lock:
            self._total += 1
            self._confidence_sum += confidence

            if source == "rule":
                self._rule_hits += 1
            elif source == "ai":
                self._ai_hits += 1
            elif source in ("fallback", "rule_fallback"):
                self._fallback_hits += 1
            else:
                self._fallback_hits += 1

            if requires_clarification:
                self._clarification_hits += 1

    def snapshot(self):
        """Return a snapshot of current metrics."""
        with self._lock:
            return IntentMetricsSnapshot(
                total=self._total,
                rule_hits=self._rule_hits,
                ai_hits=self._ai_hits,
                fallback_hits=self._fallback_hits,
                clarification_hits=self._clarification_hits,
                confidence_sum=self._confidence_sum,
            )


def percentage(value, total):
    """Return a rounded percentage."""
    if total <= 0:
        return 0.0
    return round((value / total) * 100.0, 2)


def safe_float(value):
    """Convert confidence values safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


GLOBAL_INTENT_METRICS = IntentMetricsCollector()


def get_intent_metrics():
    """Return the process-global Intent metrics collector."""
    return GLOBAL_INTENT_METRICS
