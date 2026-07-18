"""Event bus metrics."""

from dataclasses import dataclass, field


@dataclass
class EventBusMetrics:
    """Small in-memory counters for Core EventBus observability."""

    event_published: int = 0
    event_handled: int = 0
    event_failed: int = 0
    event_retried: int = 0
    dead_letter_total: int = 0
    replayed_total: int = 0
    duplicate_skipped: int = 0
    queue_size: int = 0
    handler_latency: dict = field(default_factory=dict)
    publish_latency: dict = field(default_factory=dict)

    def record_handler_latency(self, handler_name, latency_ms):
        """Record the latest and average-ish latency for one handler."""
        current = dict(self.handler_latency.get(handler_name, {}))
        count = int(current.get("count", 0)) + 1
        total = int(current.get("total_ms", 0)) + int(latency_ms)
        current.update(
            {
                "count": count,
                "total_ms": total,
                "last_ms": int(latency_ms),
                "avg_ms": int(total / count) if count else 0,
            }
        )
        self.handler_latency[handler_name] = current

    def record_publish_latency(self, latency_ms):
        """Record aggregate publish latency."""
        count = int(self.publish_latency.get("count", 0)) + 1
        total = int(self.publish_latency.get("total_ms", 0)) + int(latency_ms)
        self.publish_latency.update(
            {
                "count": count,
                "total_ms": total,
                "last_ms": int(latency_ms),
                "avg_ms": int(total / count) if count else 0,
            }
        )

    def handler_success_rate(self):
        """Return handler success rate as a percentage."""
        total = self.event_handled + self.event_failed
        if total == 0:
            return 100.0
        return round((self.event_handled / total) * 100, 2)

    def to_dict(self):
        """Return metrics as a dict."""
        return {
            "event_published": self.event_published,
            "event_handled": self.event_handled,
            "event_failed": self.event_failed,
            "event_retried": self.event_retried,
            "dead_letter_total": self.dead_letter_total,
            "replayed_total": self.replayed_total,
            "duplicate_skipped": self.duplicate_skipped,
            "queue_size": self.queue_size,
            "handler_latency": dict(self.handler_latency),
            "publish_latency": dict(self.publish_latency),
            "handler_success_rate": self.handler_success_rate(),
        }

    def to_console_lines(self):
        """Return a compact Event Bus metrics console section."""
        return [
            "========== Event Bus ==========",
            f"Published        : {self.event_published}",
            f"Handled          : {self.event_handled}",
            f"Failed           : {self.event_failed}",
            f"Retried          : {self.event_retried}",
            f"Duplicates       : {self.duplicate_skipped}",
            f"Dead Letters     : {self.dead_letter_total}",
            f"Replayed         : {self.replayed_total}",
            f"Avg Publish      : {self.publish_latency.get('avg_ms', 0)}ms",
            f"Success Rate     : {self.handler_success_rate()}%",
            "===============================",
        ]
