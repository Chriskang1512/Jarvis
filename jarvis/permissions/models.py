from dataclasses import dataclass
from enum import Enum


class PermissionLevel(str, Enum):
    """Define execution permission levels for tools."""

    SAFE = "safe"
    CONFIRM = "confirm"
    RESTRICTED = "restricted"


class PermissionStatus(str, Enum):
    """Define permission decision statuses."""

    ALLOWED = "allowed"
    DENIED = "denied"
    CONFIRM_REQUIRED = "confirm_required"


@dataclass
class PermissionDecision:
    """Represent a structured permission decision."""

    status: PermissionStatus
    level: PermissionLevel
    reason: str = ""

    @property
    def allowed(self):
        """Return whether execution may continue."""
        return self.status == PermissionStatus.ALLOWED
