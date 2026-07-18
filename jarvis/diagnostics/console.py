class DiagnosticsConsole:
    """Render diagnostics metadata as plain text."""

    def render(self, snapshot):
        """Return one diagnostics console view as text."""
        lines = []
        lines.append("======================================")
        lines.append("      JARVIS Developer Console")
        lines.append("======================================")
        lines.append("")
        append_section(lines, "Snapshot", [f"Version   : {snapshot.version}"])
        append_section(lines, "Status", [snapshot.health.overall])
        append_section(
            lines,
            "Session",
            [
                f"ID        : {snapshot.session.session_id}",
                f"Started   : {snapshot.session.start_time}",
                f"Requests  : {snapshot.session.request_count}",
                f"Convos    : {snapshot.session.conversation_count}",
            ],
        )
        append_section(
            lines,
            "Provider",
            [
                f"Name      : {snapshot.provider.provider_name}",
                f"Model     : {snapshot.provider.model}",
                f"Finish    : {snapshot.provider.finish_reason}",
                f"Usage     : {format_usage(snapshot.provider.usage)}",
                f"Created   : {snapshot.provider.created_at}",
            ],
        )
        append_section(
            lines,
            "Voice",
            [
                f"Wake      : {snapshot.pipeline.wake}",
                f"STT       : {snapshot.pipeline.stt}",
                f"LLM       : {snapshot.pipeline.llm}",
                f"TTS       : {snapshot.pipeline.tts}",
                f"Stage     : {snapshot.pipeline.current_stage}",
            ],
        )
        append_section(
            lines,
            "Intent Runtime",
            [
                f"Input     : {snapshot.intent_runtime.input_text}",
                f"Source    : {snapshot.intent_runtime.input_source}",
                f"Intent    : {snapshot.intent_runtime.detected_intent}",
                f"Tool      : {snapshot.intent_runtime.selected_tool}",
                f"Permission: {snapshot.intent_runtime.permission_status}",
                f"Result    : {snapshot.intent_runtime.execution_result}",
                f"Response  : {snapshot.intent_runtime.response}",
                f"TTS       : {snapshot.intent_runtime.tts_output}",
                f"Elapsed   : {snapshot.intent_runtime.elapsed:.2f} sec",
                f"Errors    : {format_error_logs(snapshot.intent_runtime.error_logs)}",
            ],
        )
        append_section(
            lines,
            "Performance",
            [
                f"LLM       : {snapshot.performance.llm_latency:.2f} sec",
                f"STT       : {snapshot.performance.stt_latency:.2f} sec",
                f"TTS       : {snapshot.performance.tts_latency:.2f} sec",
                f"Total     : {snapshot.performance.total_latency:.2f} sec",
            ],
        )
        append_section(
            lines,
            "Health",
            [
                f"Provider  : {snapshot.health.provider}",
                f"Voice     : {snapshot.health.voice}",
                f"Pipeline  : {snapshot.health.pipeline}",
            ],
        )
        append_section(lines, "Event Log", format_events(snapshot.events))
        lines.append("Waiting...")
        return "\n".join(lines)


def append_section(lines, title, values):
    """Append one titled section to the console output."""
    lines.append(title)
    lines.append("--------------------")
    lines.extend(values)
    lines.append("")


def format_usage(usage):
    """Format provider usage metadata for display."""
    if usage is None:
        return "not available"

    return str(usage)


def format_events(events):
    """Format diagnostics event log entries."""
    if len(events) == 0:
        return ["No events yet."]

    return [f"{event.timestamp}  {event.message}" for event in events[-10:]]


def format_error_logs(error_logs):
    """Format intent runtime errors for one-line display."""
    if len(error_logs) == 0:
        return "none"

    return " | ".join(str(error) for error in error_logs[-3:])
