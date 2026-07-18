from dataclasses import dataclass

from jarvis.integrations.bridge.errors import TIMEOUT


@dataclass
class IntegrationMetrics:
    """Runtime statistics for integration execution."""

    success_count: int = 0
    failed_count: int = 0
    timeout_count: int = 0
    total_latency_ms: int = 0

    @property
    def total_count(self):
        """Return total integration attempts."""
        return self.success_count + self.failed_count

    @property
    def average_latency_ms(self):
        """Return average latency across all attempts."""
        if self.total_count == 0:
            return 0

        return int(self.total_latency_ms / self.total_count)

    def record(self, result):
        """Record one IntegrationResult."""
        self.total_latency_ms += int(getattr(result, "duration_ms", 0) or 0)

        if getattr(result, "success", False):
            self.success_count += 1
            return

        self.failed_count += 1

        if getattr(result, "error_code", "") == TIMEOUT:
            self.timeout_count += 1

    def to_dict(self):
        """Return diagnostics-friendly metrics."""
        return {
            "success": self.success_count,
            "failed": self.failed_count,
            "timeout": self.timeout_count,
            "average_latency_ms": self.average_latency_ms,
            "total": self.total_count,
        }
