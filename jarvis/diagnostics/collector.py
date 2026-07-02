from uuid import uuid4

from jarvis.diagnostics.models import (
    DiagnosticSnapshot,
    EventLogEntry,
    HealthStatus,
    PerformanceMetadata,
    PipelineStatus,
    ProviderMetadata,
    SessionMetadata,
    current_time,
)


class DiagnosticsCollector:
    """Collect metadata from Jarvis modules for diagnostics rendering."""

    def __init__(self):
        """Create a collector with one fresh diagnostics snapshot."""
        self.snapshot = DiagnosticSnapshot(
            session=SessionMetadata(
                session_id=create_session_id(),
                start_time=current_time(),
            )
        )

    def publish_provider(self, provider_name, model, finish_reason="", usage=None, created_at=""):
        """Publish active provider metadata."""
        self.snapshot.provider = ProviderMetadata(
            provider_name=provider_name,
            model=model,
            finish_reason=finish_reason,
            usage=usage,
            created_at=created_at,
        )

    def publish_performance(self, llm_latency=0.0, total_latency=0.0, stt_latency=0.0, tts_latency=0.0):
        """Publish pipeline performance metadata."""
        self.snapshot.performance = PerformanceMetadata(
            llm_latency=llm_latency,
            total_latency=total_latency,
            stt_latency=stt_latency,
            tts_latency=tts_latency,
        )

    def publish_pipeline(self, wake="unknown", stt="unknown", llm="unknown", tts="unknown", current_stage="idle"):
        """Publish pipeline status metadata."""
        self.snapshot.pipeline = PipelineStatus(
            wake=wake,
            stt=stt,
            llm=llm,
            tts=tts,
            current_stage=current_stage,
        )

    def publish_health(self, provider="unknown", voice="unknown", pipeline="unknown", overall="unknown"):
        """Publish health status metadata."""
        self.snapshot.health = HealthStatus(
            provider=provider,
            voice=voice,
            pipeline=pipeline,
            overall=overall,
        )

    def increment_request_count(self):
        """Increase the total request count."""
        self.snapshot.session.request_count += 1

    def increment_conversation_count(self):
        """Increase the conversation count."""
        self.snapshot.session.conversation_count += 1

    def log_event(self, message):
        """Append one event to the diagnostics log."""
        self.snapshot.events.append(EventLogEntry(timestamp=current_time(), message=message))

    def get_snapshot(self):
        """Return the current diagnostics snapshot."""
        return self.snapshot


def create_session_id():
    """Create a short readable session ID."""
    return str(uuid4()).split("-", 1)[0].upper()
