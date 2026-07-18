from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class IntentContext:
    """Minimal context passed to intent parsers."""

    session_id: str = ""
    current_date: str = ""
    current_time: str = ""
    timezone: str = "Asia/Seoul"
    available_abilities: tuple[str, ...] = ()
    available_actions: tuple[str, ...] = ()
    recent_results: tuple[object, ...] = ()
    pending_action: object = None
    user_vocabulary: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredIntent:
    """Structured intent produced by rule or AI parsers."""

    intent_id: str
    ability: str
    action: str
    entities: dict = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)
    confidence: float = 0.0
    requires_clarification: bool = False
    clarification_question: str = ""
    source: str = "rule"
    raw_text: str = ""
    normalized_text: str = ""
    depends_on: int | None = None
    unsupported_reason: str = ""

    @property
    def key(self):
        """Return ability.action key."""
        return f"{self.ability}.{self.action}"


@dataclass(frozen=True)
class IntentParseResult:
    """Parser result containing one or more structured intents."""

    success: bool
    intents: tuple[StructuredIntent, ...] = ()
    source: str = ""
    confidence: float = 0.0
    requires_clarification: bool = False
    clarification_question: str = ""
    unsupported_reason: str = ""
    error_code: str = ""
    error_message: str = ""
    raw_text: str = ""
    normalized_text: str = ""
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""
    truncated: bool = False

    @property
    def first_intent(self):
        """Return first intent if present."""
        return self.intents[0] if self.intents else None


def empty_context():
    """Return a context with current local time filled."""
    now = datetime.now()
    return IntentContext(
        current_date=now.date().isoformat(),
        current_time=now.time().isoformat(timespec="seconds"),
    )
