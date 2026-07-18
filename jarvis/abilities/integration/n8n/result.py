from dataclasses import dataclass, field


@dataclass(frozen=True)
class N8nAbilityResult:
    """Ability-level result for n8n integration calls."""

    success: bool
    workflow_key: str
    action: str
    provider: str
    conversation_id: str = ""
    session_id: str = ""
    request_id: str = ""
    workflow_id: str = ""
    message: str = ""
    data: dict = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""

    def to_natural_language(self):
        """Return spoken response without raw metadata."""
        if self.success:
            return self.message or "실행했습니다."

        if self.error_code == "WORKFLOW_NOT_FOUND":
            return "지원하지 않는 자동화 요청입니다."

        if self.error_code == "INTEGRATION_DISABLED":
            return "n8n Bridge가 비활성화되어 있습니다."

        return self.error_message or "자동화 실행에 실패했습니다."
