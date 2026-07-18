from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class IntegrationRequest:
    """Request sent from Jarvis to an integration bridge."""

    workflow_key: str
    action: str
    payload: dict = field(default_factory=dict)
    permission: str = "safe"
    conversation_id: str = ""
    session_id: str = ""
    workflow_id: str = ""
    idempotency_key: str = ""
    timeout_seconds: int = 15
    max_retry: int = 0
    retry_delay_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
    request_id: str = ""

    def __post_init__(self):
        """Fill stable request defaults."""
        if self.request_id == "":
            object.__setattr__(self, "request_id", f"IR-{uuid4().hex[:10]}")

        if self.idempotency_key == "":
            object.__setattr__(self, "idempotency_key", self.request_id)

        if self.workflow_id == "":
            object.__setattr__(self, "workflow_id", self.workflow_key)
