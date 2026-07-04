from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class UnifiedResult:
    """Merged response contract for UI, Voice, and future LLM layers."""

    summary: str
    results: tuple = field(default_factory=tuple)
    warnings: tuple = field(default_factory=tuple)
    errors: tuple = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Freeze nested response values after construction."""
        object.__setattr__(self, "results", freeze_value(self.results))
        object.__setattr__(self, "warnings", freeze_value(self.warnings))
        object.__setattr__(self, "errors", freeze_value(self.errors))
        object.__setattr__(self, "metadata", freeze_value(self.metadata))

    def to_dict(self):
        """Return a stable dictionary contract."""
        return {
            "summary": self.summary,
            "results": thaw_value(self.results),
            "warnings": thaw_value(self.warnings),
            "errors": thaw_value(self.errors),
            "metadata": thaw_value(self.metadata),
        }


UnifiedResponse = UnifiedResult


@runtime_checkable
class ResultMerger(Protocol):
    """Protocol for merging completed execution outputs."""

    def merge(self, results: list, metadata: dict | None = None) -> UnifiedResult:
        """Merge completed execution results into a unified response."""
        ...


def result_merge_timestamp():
    """Return an ISO timestamp for merge metadata."""
    return datetime.now().isoformat(timespec="milliseconds")


def freeze_value(value):
    """Recursively freeze merge output containers."""
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: freeze_value(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)

    return value


def thaw_value(value):
    """Recursively convert frozen containers to serializable dictionaries."""
    if isinstance(value, MappingProxyType):
        return {
            key: thaw_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [thaw_value(item) for item in value]

    return value
