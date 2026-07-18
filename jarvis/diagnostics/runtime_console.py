class RuntimeDevConsole:
    """Render one RuntimeResult as a readable developer console block."""

    def render(self, result=None, theme="simple", fallback="", response=None, provider="", conversation=None):
        """Return a developer-friendly runtime summary."""
        if theme != "simple":
            raise ValueError(f"Unknown runtime console theme: {theme}")

        return render_simple(
            result=result,
            fallback=fallback,
            response=response,
            provider=provider,
            conversation=conversation,
        )


def render_simple(result=None, fallback="", response=None, provider="", conversation=None):
    """Render the simple runtime console theme."""
    lines = [SEPARATOR]
    lines.extend(render_header(result))
    lines.append(SEPARATOR)
    lines.extend(render_provider(provider))
    lines.extend(render_conversation(conversation))
    lines.extend(render_input(result))
    lines.extend(render_intent(result))
    lines.extend(render_plan(result))
    lines.extend(render_permission(result))
    lines.extend(render_tool(result))
    lines.extend(render_fallback(result, fallback))
    lines.extend(render_response(result, response))
    lines.extend(render_execution(result))
    lines.extend(render_elapsed(result))
    lines.append(SEPARATOR)
    return "\n".join(lines)


SEPARATOR = "\u2501" * 30
RUNTIME_VERSION = "v0.5.0 Beta.5.3"


def render_header(result):
    """Render runtime version and identifiers."""
    return [
        "Jarvis Runtime",
        RUNTIME_VERSION,
        "",
        "Runtime ID",
        read_runtime_id(result) or "unknown",
        "",
        "Session",
        read_session_id(result) or "unknown",
        "",
    ]


def render_provider(provider):
    """Render the active chat provider."""
    if provider == "":
        provider = "unknown"

    return [
        "Provider",
        format_provider_name(provider),
        "",
    ]


def render_conversation(conversation):
    """Render voice conversation lifecycle state."""
    if conversation is None:
        return []

    return [
        "Conversation",
        "Session",
        getattr(conversation, "session_id", "unknown"),
        "",
        "State",
        format_conversation_state(getattr(conversation, "state", "unknown")),
        "",
        "Remaining",
        f"{get_conversation_remaining(conversation):.1f} sec",
        "",
    ]


def format_conversation_state(state):
    """Return a console-friendly lifecycle state."""
    labels = {
        "IDLE": "Idle",
        "LISTENING": "Listening",
        "THINKING": "Thinking",
        "SPEAKING": "Speaking",
        "FOLLOW_UP": "Follow-up",
        "CLOSED": "Closed",
    }
    return labels.get(state, str(state))


def get_conversation_remaining(conversation):
    """Return remaining follow-up seconds for display."""
    if hasattr(conversation, "remaining_follow_up_seconds"):
        return conversation.remaining_follow_up_seconds()

    return 0.0


def format_provider_name(provider):
    """Format provider IDs for console display."""
    provider_names = {
        "mock": "Mock",
        "openai": "OpenAI",
        "claude": "Claude",
    }
    return provider_names.get(provider, provider)


def render_input(result):
    """Render input text."""
    return [
        "\U0001f3a4 Input",
        read_input_text(result),
        "",
    ]


def render_intent(result):
    """Render intent metadata."""
    intent = getattr(result, "intent", None)

    if intent is None:
        return [
            "\U0001f9e0 Intent",
            "unmatched",
            "confidence: 0.00",
            "source: unknown",
            "",
        ]

    return [
        "\U0001f9e0 Intent",
        intent.name,
        f"confidence: {intent.confidence:.2f}",
        f"source: {intent.source}",
        "",
    ]


def render_permission(result):
    """Render permission decision."""
    permission = getattr(result, "permission", None)

    if permission is None:
        return [
            "\U0001f510 Permission",
            "unknown / unknown",
            "reason: n/a",
            "",
        ]

    level = getattr(permission, "level", "")
    status = getattr(permission, "status", "")
    reason = getattr(permission, "reason", "")
    allowed = "allowed" if getattr(permission, "allowed", False) else "blocked"

    return [
        "\U0001f510 Permission",
        f"{format_enum(level)} / {format_enum(status)} / {allowed}",
        f"reason: {reason or 'n/a'}",
        "",
    ]


def render_plan(result):
    """Render generated plan details."""
    plan = read_plan(result)

    if plan is None:
        return [
            "Plan",
            "none",
            "",
        ]

    steps = getattr(plan, "steps", ())
    lines = [
        "Plan",
        "ID",
        getattr(plan, "id", ""),
        "",
        "Goal",
        getattr(plan, "goal", ""),
        "",
        "Steps",
    ]

    if len(steps) == 0:
        lines.append("none")
        lines.append("")
        return lines

    for index, step in enumerate(steps, start=1):
        lines.append(f"[{index}] {getattr(step, 'tool', '')}")
        lines.append(f"Status : {getattr(step, 'status', '')}")

    lines.append("")
    return lines


def render_tool(result):
    """Render resolved tool details."""
    tool_name = read_tool_name(result)
    resolved = "true" if tool_name != "" else "false"

    return [
        "\U0001f9f0 Tool",
        tool_name or "none",
        f"resolved: {resolved}",
        "",
    ]


def render_fallback(result, fallback):
    """Render fallback details when the runtime did not handle the input."""
    if fallback == "" and result is not None and not getattr(result, "handled", False):
        fallback = "llm"

    if fallback == "":
        return []

    return [
        "\u21a9 Fallback",
        fallback,
        "",
    ]


def render_response(result, response):
    """Render response text."""
    if response is None and result is not None:
        response = getattr(result, "response", "")

    return [
        "\U0001f916 Response",
        str(response or ""),
        "",
    ]


def render_elapsed(result):
    """Render elapsed runtime milliseconds."""
    elapsed = 0.0

    if result is not None:
        elapsed = getattr(result, "elapsed", 0.0)
        diagnostics = getattr(result, "diagnostics", None)

        if elapsed == 0.0 and diagnostics is not None:
            elapsed = getattr(diagnostics, "elapsed", 0.0)

    return [
        "\u23f1 Elapsed",
        f"{int(elapsed * 1000)}ms",
        "",
    ]


def render_execution(result):
    """Render execution metrics."""
    metrics = read_metrics(result)
    fallback_used = read_fallback_used(result, metrics)

    return [
        "Execution",
        f"Execution Time : {format_ms(read_metric(metrics, 'execution_time'))}",
        f"Router Time    : {format_ms(read_metric(metrics, 'router_time'))}",
        f"Dispatcher Time: {format_ms(read_metric(metrics, 'dispatcher_time'))}",
        "",
        "Retry",
        f"Count : {read_metric(metrics, 'retry_count')}",
        "",
        "Timeout",
        "configured per step",
        "",
        "Fallback",
        "used: true" if fallback_used else "used: false",
        "",
    ]


def read_input_text(result):
    """Read input text from RuntimeResult diagnostics."""
    if result is None:
        return ""

    diagnostics = getattr(result, "diagnostics", None)

    if diagnostics is not None and getattr(diagnostics, "input_text", "") != "":
        return diagnostics.input_text

    intent = getattr(result, "intent", None)

    if intent is not None:
        return getattr(intent, "raw_text", "")

    return ""


def read_tool_name(result):
    """Read resolved tool name from RuntimeResult."""
    if result is None:
        return ""

    tool_name = getattr(result, "tool", "")

    if tool_name != "":
        return tool_name

    return getattr(result, "tool_name", "")


def read_plan(result):
    """Read plan from RuntimeResult."""
    if result is None:
        return None

    plan = getattr(result, "plan", None)

    if plan is not None:
        return plan

    diagnostics = getattr(result, "diagnostics", None)

    if diagnostics is None:
        return None

    return getattr(diagnostics, "plan", None)


def read_metrics(result):
    """Read execution metrics from RuntimeResult diagnostics."""
    if result is None:
        return None

    diagnostics = getattr(result, "diagnostics", None)

    if diagnostics is not None and getattr(diagnostics, "metrics", None) is not None:
        return diagnostics.metrics

    return result


def read_metric(metrics, key):
    """Read a metric from object-like values."""
    if metrics is None:
        return 0

    return getattr(metrics, key, 0)


def read_fallback_used(result, metrics):
    """Return whether fallback was used."""
    if result is not None and getattr(result, "fallback_used", False):
        return True

    return bool(read_metric(metrics, "fallback_used"))


def format_ms(seconds):
    """Format seconds as whole milliseconds."""
    return f"{int(float(seconds or 0) * 1000)}ms"


def read_runtime_id(result):
    """Read runtime ID from RuntimeResult diagnostics."""
    if result is None:
        return ""

    diagnostics = getattr(result, "diagnostics", None)

    if diagnostics is None:
        return ""

    return getattr(diagnostics, "runtime_id", "")


def read_session_id(result):
    """Read session ID from RuntimeResult context."""
    if result is None:
        return ""

    diagnostics = getattr(result, "diagnostics", None)

    if diagnostics is None:
        return ""

    context = getattr(diagnostics, "context", None)

    if context is None:
        return ""

    return getattr(context, "session_id", "")


def format_enum(value):
    """Format enum-like values for display."""
    if hasattr(value, "value"):
        return str(value.value)

    return str(value)
