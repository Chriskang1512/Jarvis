from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntegrationQuery:
    """Parsed integration workflow request."""

    workflow_key: str
    action: str
    payload: dict = field(default_factory=dict)
    raw_text: str = ""
    conversation_id: str = ""
    session_id: str = ""
    workflow_id: str = ""
    idempotency_key: str = ""
    max_retry: int = 0
    retry_delay_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
