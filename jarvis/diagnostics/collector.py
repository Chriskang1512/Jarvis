from uuid import uuid4

from jarvis.diagnostics.models import (
    DiagnosticSnapshot,
    EventLogEntry,
    HealthStatus,
    IntentRuntimeStatus,
    PerformanceMetadata,
    PipelineStatus,
    PublishedEvent,
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

    def publish_intent_runtime(
        self,
        input_text=None,
        input_source=None,
        detected_intent=None,
        selected_tool=None,
        permission_status=None,
        execution_result=None,
        response=None,
        tts_output=None,
        error=None,
        elapsed=None,
    ):
        """Publish v0.5 intent runtime trace metadata."""
        current = self.snapshot.intent_runtime
        error_logs = list(current.error_logs)

        if error not in [None, ""]:
            error_logs.append(str(error))

        self.snapshot.intent_runtime = IntentRuntimeStatus(
            input_text=choose_value(input_text, current.input_text),
            input_source=choose_value(input_source, current.input_source),
            detected_intent=choose_value(detected_intent, current.detected_intent),
            selected_tool=choose_value(selected_tool, current.selected_tool),
            permission_status=choose_value(permission_status, current.permission_status),
            execution_result=choose_value(execution_result, current.execution_result),
            response=choose_value(response, current.response),
            tts_output=choose_value(tts_output, current.tts_output),
            error_logs=error_logs[-10:],
            elapsed=choose_value(elapsed, current.elapsed),
        )

    def publish(self, event_type, payload):
        """Publish a generic collector event for diagnostics/history subscribers."""
        self.snapshot.published_events.append(
            PublishedEvent(
                event_type=str(event_type),
                payload=dict(payload),
                timestamp=current_time(),
            )
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


def choose_value(new_value, current_value):
    """Keep the current value when no new value is provided."""
    if new_value is None:
        return current_value

    return new_value
