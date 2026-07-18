from dataclasses import dataclass, field

from jarvis.permissions import PermissionLevel


@dataclass(frozen=True)
class WorkflowDefinition:
    """Describe one allowed integration workflow."""

    key: str
    provider: str = "n8n"
    permission: PermissionLevel = PermissionLevel.SAFE
    enabled: bool = True
    timeout_seconds: int = 15
    max_retry: int = 0
    retry_delay_seconds: float = 0.0
    webhook_path: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)


class WorkflowRegistry:
    """Allow-list registry for external workflow execution."""

    def __init__(self, workflows=None):
        """Create registry from default and optional workflows."""
        self.workflows = {}

        for workflow in workflows or default_workflows():
            self.register(workflow)

    def register(self, workflow):
        """Register one workflow definition."""
        self.workflows[workflow.key] = workflow

    def get(self, workflow_key):
        """Return one workflow definition."""
        return self.workflows.get(str(workflow_key or ""))

    def exists(self, workflow_key):
        """Return whether a workflow exists."""
        return self.get(workflow_key) is not None

    def list(self):
        """Return workflows sorted by key."""
        return [self.workflows[key] for key in sorted(self.workflows)]


def default_workflows():
    """Return Sprint 7 foundation workflows."""
    return [
        WorkflowDefinition(
            key="system.echo",
            permission=PermissionLevel.SAFE,
            enabled=True,
            timeout_seconds=15,
            webhook_path="/webhook/jarvis/system.echo",
            capabilities=("system", "echo", "health"),
        ),
        WorkflowDefinition(
            key="system.health",
            permission=PermissionLevel.SAFE,
            enabled=True,
            timeout_seconds=15,
            webhook_path="/webhook/jarvis/system.health",
            capabilities=("system", "health"),
        ),
        WorkflowDefinition(
            key="notification.test",
            permission=PermissionLevel.CONFIRM,
            enabled=True,
            timeout_seconds=20,
            webhook_path="/webhook/jarvis/notification.test",
            capabilities=("notification", "test"),
        ),
    ]
