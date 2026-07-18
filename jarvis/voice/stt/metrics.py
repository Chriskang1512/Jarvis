import os
import threading
from dataclasses import dataclass, field

from jarvis.debug_trace import read_env_file_value, trace_event
from jarvis.voice.stt.models import TranscriptResult


@dataclass(frozen=True)
class STTMetricsSnapshot:
    """Point-in-time STT runtime metrics."""

    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    fallback_count: int = 0
    correction_count: int = 0
    confirmation_failure_count: int = 0
    total_latency_ms: int = 0
    provider_requests: dict = field(default_factory=dict)
    provider_success: dict = field(default_factory=dict)
    provider_failure: dict = field(default_factory=dict)

    @property
    def success_rate(self):
        """Return overall success percentage."""
        return percentage(self.success_count, self.total_requests)

    @property
    def failure_rate(self):
        """Return overall failure percentage."""
        return percentage(self.failure_count, self.total_requests)

    @property
    def fallback_rate(self):
        """Return fallback usage percentage."""
        return percentage(self.fallback_count, self.total_requests)

    @property
    def correction_rate(self):
        """Return correction usage percentage."""
        return percentage(self.correction_count, self.total_requests)

    @property
    def avg_latency_ms(self):
        """Return average STT latency."""
        if self.total_requests == 0:
            return 0

        return int(self.total_latency_ms / self.total_requests)


class STTMetrics:
    """Thread-safe in-process STT metrics accumulator."""

    def __init__(self):
        self._lock = threading.RLock()
        self.reset()

    def reset(self):
        """Clear all metric counters."""
        with self._lock:
            self._total_requests = 0
            self._success_count = 0
            self._failure_count = 0
            self._fallback_count = 0
            self._correction_count = 0
            self._confirmation_failure_count = 0
            self._total_latency_ms = 0
            self._provider_requests = {}
            self._provider_success = {}
            self._provider_failure = {}

    def record(self, result, expected_answer_type="", confirmation_decision=""):
        """Record one TranscriptResult."""
        provider = result.provider or "unknown"

        with self._lock:
            self._total_requests += 1
            self._total_latency_ms += int(result.latency_ms or 0)
            self._provider_requests[provider] = self._provider_requests.get(provider, 0) + 1

            if result.success:
                self._success_count += 1
                self._provider_success[provider] = self._provider_success.get(provider, 0) + 1
            else:
                self._failure_count += 1
                self._provider_failure[provider] = self._provider_failure.get(provider, 0) + 1

            if result.fallback_used:
                self._fallback_count += 1

            if result.correction_applied:
                self._correction_count += 1

            if expected_answer_type == "confirmation" and confirmation_decision in ["", "unknown", None]:
                self._confirmation_failure_count += 1

    def snapshot(self):
        """Return an immutable metrics snapshot."""
        with self._lock:
            return STTMetricsSnapshot(
                total_requests=self._total_requests,
                success_count=self._success_count,
                failure_count=self._failure_count,
                fallback_count=self._fallback_count,
                correction_count=self._correction_count,
                confirmation_failure_count=self._confirmation_failure_count,
                total_latency_ms=self._total_latency_ms,
                provider_requests=dict(self._provider_requests),
                provider_success=dict(self._provider_success),
                provider_failure=dict(self._provider_failure),
            )


GLOBAL_STT_METRICS = STTMetrics()


def record_stt_result(result, expected_answer_type="", confirmation_decision=""):
    """Record a result and emit concise metrics when enabled."""
    if not is_stt_metrics_enabled():
        return

    GLOBAL_STT_METRICS.record(
        result,
        expected_answer_type=expected_answer_type,
        confirmation_decision=confirmation_decision,
    )
    snapshot = GLOBAL_STT_METRICS.snapshot()
    trace_event(
        "voice.stt.stats",
        total=snapshot.total_requests,
        success_rate=round(snapshot.success_rate, 1),
        failure_rate=round(snapshot.failure_rate, 1),
        fallback_rate=round(snapshot.fallback_rate, 1),
        correction_rate=round(snapshot.correction_rate, 1),
        avg_latency_ms=snapshot.avg_latency_ms,
        provider=result.provider or "unknown",
        provider_requests=snapshot.provider_requests.get(result.provider or "unknown", 0),
        confirmation_failures=snapshot.confirmation_failure_count,
    )


def get_stt_metrics_snapshot():
    """Return current STT metrics."""
    return GLOBAL_STT_METRICS.snapshot()


def render_stt_metrics_console(snapshot=None, provider=""):
    """Return a readable STT metrics console block."""
    snapshot = snapshot or get_stt_metrics_snapshot()
    provider_label = provider or most_used_provider(snapshot) or "-"

    return "\n".join(
        [
            "========== STT ==========",
            f"Provider        : {provider_label}",
            f"Requests        : {snapshot.total_requests}",
            f"Success         : {snapshot.success_count} ({snapshot.success_rate}%)",
            f"Failure         : {snapshot.failure_count} ({snapshot.failure_rate}%)",
            f"Fallback        : {snapshot.fallback_count} ({snapshot.fallback_rate}%)",
            f"Average Latency : {snapshot.avg_latency_ms / 1000:.2f}s",
            f"Correction      : {snapshot.correction_count} ({snapshot.correction_rate}%)",
            f"Confirm Fail    : {snapshot.confirmation_failure_count}",
            "=========================",
        ]
    )


def reset_stt_metrics():
    """Clear global STT metrics."""
    GLOBAL_STT_METRICS.reset()


def is_stt_metrics_enabled():
    """Return whether STT metrics collection is enabled."""
    value = os.environ.get("JARVIS_STT_METRICS_ENABLED", "")

    if value == "":
        value = read_env_file_value("JARVIS_STT_METRICS_ENABLED")

    if value == "":
        return True

    return value.lower() in ["1", "true", "yes", "on"]


def percentage(value, total):
    """Return a rounded percentage."""
    if total == 0:
        return 0.0

    return round((value / total) * 100, 1)


def most_used_provider(snapshot):
    """Return the provider with the most requests."""
    if not snapshot.provider_requests:
        return ""

    return max(snapshot.provider_requests.items(), key=lambda item: item[1])[0]
