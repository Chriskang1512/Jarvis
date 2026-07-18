from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntegrationResult:
    """Normalized result returned by any integration bridge."""

    success: bool
    request_id: str
    workflow_key: str
    action: str
    conversation_id: str = ""
    session_id: str = ""
    workflow_id: str = ""
    status: str = ""
    data: dict = field(default_factory=dict)
    message: str = ""
    provider: str = ""
    duration_ms: int = 0
    retryable: bool = False
    retry_count: int = 0
    error_code: str = ""
    error_message: str = ""
    raw_response_metadata: dict = field(default_factory=dict)

    def to_natural_language(self):
        """Return a safe spoken response."""
        if self.success:
            return self.message or "실행했습니다."

        if self.error_code == "INTEGRATION_DISABLED":
            return "n8n Bridge가 비활성화되어 있습니다."

        if self.error_code == "WORKFLOW_NOT_FOUND":
            return "지원하지 않는 자동화 요청입니다."

        if self.error_code == "PERMISSION_DENIED":
            return "이 자동화는 권한 때문에 실행할 수 없습니다."

        return self.error_message or "자동화 실행에 실패했습니다."
