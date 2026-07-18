from jarvis.permissions.models import (
    PermissionDecision,
    PermissionLevel,
    PermissionStatus,
)


class PermissionLayer:
    """Evaluate whether a tool may be executed."""

    def __init__(self, diagnostics_collector=None):
        """Create a permission layer with optional diagnostics."""
        self.diagnostics_collector = diagnostics_collector

    def evaluate(self, tool, request=None):
        """Return a permission decision for one tool request."""
        self.log_event("permission.check.started")

        try:
            level = normalize_permission_level(tool.metadata.permission_level)
        except ValueError as error:
            self.log_event("permission.failed")
            return PermissionDecision(
                status=PermissionStatus.DENIED,
                level=PermissionLevel.RESTRICTED,
                reason=str(error),
            )

        if level == PermissionLevel.SAFE:
            self.log_event("permission.allowed")
            return PermissionDecision(
                status=PermissionStatus.ALLOWED,
                level=level,
                reason="Safe tool execution is allowed.",
            )

        if level == PermissionLevel.CONFIRM:
            if request is not None and request.input_data.get("_confirmed") is True:
                self.log_event("permission.confirm.approved")
                return PermissionDecision(
                    status=PermissionStatus.ALLOWED,
                    level=level,
                    reason="Tool execution was confirmed.",
                )

            self.log_event("permission.confirm.required")
            return PermissionDecision(
                status=PermissionStatus.CONFIRM_REQUIRED,
                level=level,
                reason="Tool execution requires confirmation.",
            )

        self.log_event("permission.denied")
        return PermissionDecision(
            status=PermissionStatus.DENIED,
            level=level,
            reason="Tool execution is restricted.",
        )

    def log_event(self, message):
        """Publish a permission diagnostics event."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def normalize_permission_level(level):
    """Return a PermissionLevel from enum or string input."""
    if isinstance(level, PermissionLevel):
        return level

    try:
        return PermissionLevel(str(level).lower())
    except ValueError as error:
        raise ValueError(f"Unknown permission level: {level}") from error
