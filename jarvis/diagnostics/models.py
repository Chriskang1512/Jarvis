from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionMetadata:
    """Store metadata for one Jarvis runtime session."""

    session_id: str = ""
    start_time: str = ""
    request_count: int = 0
    conversation_count: int = 0


@dataclass
class ProviderMetadata:
    """Store metadata about the active AI provider."""

    provider_name: str = ""
    model: str = ""
    finish_reason: str = ""
    usage: object = None
    created_at: str = ""


@dataclass
class PerformanceMetadata:
    """Store timing metadata for the Jarvis pipeline."""

    llm_latency: float = 0.0
    total_latency: float = 0.0
    stt_latency: float = 0.0
    tts_latency: float = 0.0


@dataclass
class PipelineStatus:
    """Store the current status of each pipeline stage."""

    wake: str = "unknown"
    stt: str = "unknown"
    llm: str = "unknown"
    tts: str = "unknown"
    current_stage: str = "idle"


@dataclass
class HealthStatus:
    """Store simple health status for major Jarvis systems."""

    provider: str = "unknown"
    voice: str = "unknown"
    pipeline: str = "unknown"
    overall: str = "unknown"


@dataclass
class EventLogEntry:
    """Store one diagnostics event log entry."""

    timestamp: str
    message: str


@dataclass
class DiagnosticSnapshot:
    """Store one complete diagnostics snapshot."""

    version: int = 1
    session: SessionMetadata = field(default_factory=SessionMetadata)
    provider: ProviderMetadata = field(default_factory=ProviderMetadata)
    performance: PerformanceMetadata = field(default_factory=PerformanceMetadata)
    pipeline: PipelineStatus = field(default_factory=PipelineStatus)
    health: HealthStatus = field(default_factory=HealthStatus)
    events: list = field(default_factory=list)


def current_time():
    """Return the current local time for diagnostics display."""
    return datetime.now().strftime("%H:%M:%S")
