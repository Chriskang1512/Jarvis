from dataclasses import dataclass, field
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class BaseAbilityResult:
    """Common fields for durable Ability-specific result contracts."""

    success: bool
    provider: str = ""
    execution_time_ms: int = 0
    trace_id: str = ""
    correlation_id: str = ""
    error_code: str = ""


@dataclass(frozen=True)
class AbilityResult(Generic[T]):
    """Standard result envelope returned by every Ability."""

    success: bool
    data: T = None
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_natural_language(self):
        """Return a spoken response when the wrapped data supports it."""
        if not self.success:
            return self.error

        if hasattr(self.data, "to_natural_language"):
            return self.data.to_natural_language()

        return str(self.data)


@dataclass(frozen=True)
class AbilityHealth:
    """Health status for one Ability and its provider boundary."""

    status: str
    provider: str = ""
    message: str = ""

    @property
    def ok(self):
        """Return whether the ability is ready to serve requests."""
        return self.status.lower() == "ok"
