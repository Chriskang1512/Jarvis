from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IntegrationHealth:
    """Health status for one integration provider."""

    provider: str
    enabled: bool
    reachable: bool = False
    authenticated: bool = False
    latency_ms: int = 0
    checked_at: str = ""
    error: str = ""

    def __post_init__(self):
        """Fill checked_at when omitted."""
        if self.checked_at == "":
            object.__setattr__(self, "checked_at", datetime.now().isoformat(timespec="seconds"))

    @property
    def ok(self):
        """Return whether the provider is usable."""
        return self.enabled and self.reachable and self.authenticated and self.error == ""
