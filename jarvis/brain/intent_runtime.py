from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from time import perf_counter
from uuid import uuid4

from jarvis.date_calculator import current_time, get_runtime_timezone, today
from jarvis.brain.execution_engine import EXECUTION_STATUS_CANCELLED, EXECUTION_STATUS_COMPLETED
from jarvis.brain.execution_engine import EXECUTION_STATUS_FAILED, ExecutionContext, RetryPolicy
from jarvis.brain.execution_engine import create_metrics, execute_parallel
from jarvis.brain.planner import Planner, STEP_STATUS_COMPLETED, STEP_STATUS_FAILED
from jarvis.brain.planner import STEP_STATUS_RUNNING, update_plan_step_status
from jarvis.tools.router import (
    RegistryToolRouter,
    ToolRoute,
    build_input_data,
    find_matched_prefix,
    is_arithmetic_expression,
    score_metadata_match,
)
from jarvis.permissions import PermissionStatus
from jarvis.tools import ToolRequest


DEFAULT_MIN_CONFIDENCE = 0.75


@dataclass(frozen=True)
class RuntimeContext:
    """Source-agnostic runtime input context."""

    text: str
    source: str = "text"
    language: str = ""
    session_id: str = ""
    user_id: str = ""
    wake_word: str = ""
    conversation_id: str = ""
    timestamp: str = ""
    current_date: str = ""
    current_time: str = ""
    timezone: str = ""

    def __post_init__(self):
        """Fill stable defaults for replay-friendly context."""
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "source", str(self.source or "text"))

        if self.timestamp == "":
            object.__setattr__(self, "timestamp", datetime.now().isoformat(timespec="seconds"))

        if self.timezone == "":
            object.__setattr__(self, "timezone", get_runtime_timezone())

        if self.current_date == "":
            object.__setattr__(self, "current_date", today(timezone=self.timezone))

        if self.current_time == "":
            object.__setattr__(self, "current_time", current_time(timezone=self.timezone))

    def to_dict(self):
        """Return a stable dictionary payload for subscribers."""
        return {
            "text": self.text,
            "source": self.source,
            "language": self.language,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "wake_word": self.wake_word,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp,
            "current_date": self.current_date,
            "current_time": self.current_time,
            "timezone": self.timezone,
        }


@dataclass(frozen=True)
class Intent:
    """Standard intent contract shared by Voice, Text, CLI, and API inputs."""

    name: str
    confidence: float
    source: str = "keyword"
    parameters: dict = field(default_factory=dict)
    raw_text: str = ""
    tool_name: str = ""
    permission_level: object = ""

    def __post_init__(self):
        """Freeze mapping fields so replay diagnostics cannot drift."""
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def to_dict(self):
        """Return a serializable intent payload."""
        return intent_to_dict(self)


@dataclass(frozen=True)
class RuntimeDiagnostics:
    """Diagnostics payload produced by one runtime turn."""

    input_text: str = ""
    input_source: str = "text"
    detected_intent: str = ""
    selected_tool: str = ""
    permission_status: str = ""
    execution_result: str = ""
    error_logs: tuple = ()
    elapsed: float = 0.0
    runtime_id: str = ""
    plan: object = None
    metrics: object = None
    context: RuntimeContext | None = None

    def to_dict(self):
        """Return a stable dictionary payload for collectors."""
        return {
            "input_text": self.input_text,
            "input_source": self.input_source,
            "detected_intent": self.detected_intent,
            "selected_tool": self.selected_tool,
            "permission_status": self.permission_status,
            "execution_result": self.execution_result,
            "error_logs": list(self.error_logs),
            "elapsed": self.elapsed,
            "runtime_id": self.runtime_id,
            "plan": plan_to_dict(self.plan),
            "metrics": metrics_to_dict(self.metrics),
            "context": None if self.context is None else self.context.to_dict(),
        }


@dataclass(frozen=True)
class RuntimeResult:
    """Result of the shared v0.5 intent runtime."""

    handled: bool
    intent: Intent | None = None
    permission: object = None
    tool: str = ""
    response: object = ""
    plan: object = None
    diagnostics: RuntimeDiagnostics = field(default_factory=RuntimeDiagnostics)
    elapsed: float = 0.0
    tool_name: str = ""
    permission_status: str = ""
    success: bool = False
    error: str = ""
    status: str = ""
    execution_time: float = 0.0
    router_time: float = 0.0
    dispatcher_time: float = 0.0
    retry_count: int = 0
    fallback_used: bool = False
    tool_output: object = None
    task: object = None


ParsedIntent = Intent
IntentRuntimeResult = RuntimeResult


class IntentParser:
    """Parse user text into executable intents using registry metadata."""

    def __init__(self, min_confidence=DEFAULT_MIN_CONFIDENCE, source="keyword"):
        """Create an exchangeable parser with a route confidence threshold."""
        self.min_confidence = min_confidence
        self.source = source

    def parse(self, message, registry):
        """Return the best parsed intent, or None when no tool is clear."""
        text = strip_wake_word(message)

        if text == "" or registry is None:
            return None

        candidates = []

        for tool in registry.list():
            if tool.metadata.deprecated:
                continue

            candidate = create_intent_candidate(tool, text, self.source)

            if candidate is not None:
                candidates.append(candidate)

        if len(candidates) == 0:
            return None

        candidates.sort(
            key=lambda candidate: (
                candidate.intent.confidence,
                candidate.priority,
            ),
            reverse=True,
        )

        selected = candidates[0].intent

        if selected.confidence < self.min_confidence:
            return None

        return selected


@dataclass(frozen=True)
class IntentCandidate:
    """Internal scored intent candidate."""

    intent: Intent
    priority: int


IntentRoute = ToolRoute
IntentToolRouter = RegistryToolRouter


@dataclass
class IntentPermissionSubject:
    """Minimal permission subject used before tool routing."""

    permission_level: object

    @property
    def metadata(self):
        """Expose metadata-like shape for PermissionLayer."""
        return self


class IntentRuntime:
    """Run Input -> Intent -> Permission -> Router -> Dispatcher -> Response."""

    def __init__(
        self,
        tool_dispatcher,
        intent_parser=None,
        planner=None,
        tool_router=None,
        retry_policy=None,
        diagnostics_collector=None,
    ):
        """Create a source-agnostic runtime from existing tool infrastructure."""
        self.tool_dispatcher = tool_dispatcher
        self.intent_parser = intent_parser or IntentParser()
        self.planner = planner or Planner()
        self.tool_router = tool_router or RegistryToolRouter(tool_dispatcher.registry)
        self.retry_policy = retry_policy or RetryPolicy()
        self.diagnostics_collector = diagnostics_collector

    def run(self, context, input_source=None):
        """Run one shared runtime turn for Voice, Text, CLI, API, or integrations."""
        runtime_context = normalize_runtime_context(context, input_source)
        runtime_id = create_runtime_id()
        started = perf_counter()
        self.publish_event(
            "runtime.started",
            {
                "runtime_id": runtime_id,
                "context": runtime_context.to_dict(),
            },
        )
        self.publish_runtime(input_text=runtime_context.text, input_source=runtime_context.source)
        self.log_event("intent.parse.started")

        intent = self.intent_parser.parse(runtime_context.text, self.tool_dispatcher.registry)

        if intent is None:
            self.log_event("intent.parse.unmatched")
            self.publish_runtime(detected_intent="unmatched")
            self.publish_event("intent.parsed", {"intent": None, "matched": False})
            return self.finish_result(
                RuntimeResult(handled=False),
                context=runtime_context,
                runtime_id=runtime_id,
                started=started,
                detected_intent="unmatched",
                fallback_used=True,
            )

        self.log_event("intent.parse.matched")
        self.publish_runtime(detected_intent=intent.name)
        self.publish_event("intent.parsed", {"intent": intent_to_dict(intent), "matched": True})
        plan = self.planner.plan(intent)
        self.publish_event("plan.created", {"plan": plan_to_dict(plan)})
        self.publish_event("plan.started", {"plan": plan_to_dict(plan)})

        if plan is None or len(plan.steps) == 0:
            self.publish_event("plan.completed", {"plan": plan_to_dict(plan), "success": False})
            return self.finish_result(
                RuntimeResult(
                    handled=False,
                    intent=intent,
                    plan=plan,
                ),
                context=runtime_context,
                runtime_id=runtime_id,
                plan=plan,
                started=started,
                detected_intent=intent.name,
                execution_result="empty_plan",
                fallback_used=True,
            )

        request = ToolRequest(tool_name=intent.name, input_data=dict(intent.parameters))
        permission_decision = self.evaluate_intent_permission(intent, request)
        self.publish_runtime(permission_status=permission_decision.status.value)
        self.publish_event(
            "permission.checked",
            {
                "intent": intent_to_dict(intent),
                "status": permission_decision.status.value,
                "level": permission_decision.level.value,
                "reason": permission_decision.reason,
            },
        )

        if permission_decision.status == PermissionStatus.CONFIRM_REQUIRED:
            response = "이 작업은 확인이 필요합니다."
            self.log_event("intent.permission.confirm_required")
            self.publish_runtime(response=response)
            self.publish_event("response.generated", {"response": response, "success": False})
            self.publish_event("plan.completed", {"plan": plan_to_dict(plan), "success": False})
            return self.finish_result(
                RuntimeResult(
                    handled=True,
                    intent=intent,
                    permission=permission_decision,
                    response=response,
                    permission_status=permission_decision.status.value,
                    success=False,
                    error=permission_decision.reason,
                ),
                context=runtime_context,
                runtime_id=runtime_id,
                plan=plan,
                started=started,
                detected_intent=intent.name,
                permission_status=permission_decision.status.value,
            )

        if not permission_decision.allowed:
            response = f"권한이 없어 실행할 수 없습니다: {permission_decision.reason}"
            self.log_event("intent.permission.denied")
            self.publish_runtime(response=response, error=permission_decision.reason)
            self.publish_event("response.generated", {"response": response, "success": False})
            self.publish_event("plan.completed", {"plan": plan_to_dict(plan), "success": False})
            return self.finish_result(
                RuntimeResult(
                    handled=True,
                    intent=intent,
                    permission=permission_decision,
                    response=response,
                    permission_status=permission_decision.status.value,
                    success=False,
                    error=permission_decision.reason,
                ),
                context=runtime_context,
                runtime_id=runtime_id,
                plan=plan,
                started=started,
                detected_intent=intent.name,
                permission_status=permission_decision.status.value,
                error_logs=[permission_decision.reason],
            )

        plan_result = self.execute_plan(plan, intent, started)
        executed_plan = plan_result["plan"]
        route = plan_result["route"]
        tool_result = plan_result["tool_result"]

        if route is None:
            error = plan_result["error"]
            response = format_runtime_error_response(error)
            self.log_event("intent.tool.missing")
            self.publish_runtime(error=error)
            self.publish_event("response.generated", {"response": response, "success": False})
            self.publish_event("plan.completed", {"plan": plan_to_dict(executed_plan), "success": False})
            return self.finish_result(
                RuntimeResult(
                    handled=True,
                    intent=intent,
                    permission=permission_decision,
                    plan=executed_plan,
                    response=response,
                    permission_status=permission_decision.status.value,
                    success=False,
                    error=error,
                ),
                context=runtime_context,
                runtime_id=runtime_id,
                plan=executed_plan,
                started=started,
                detected_intent=intent.name,
                permission_status=permission_decision.status.value,
                error_logs=[error],
                metrics=plan_result["metrics"],
            )

        if not tool_result.success:
            response = format_runtime_error_response(tool_result.error)
            self.publish_runtime(execution_result="failed", response=response, error=tool_result.error)
            self.publish_event("response.generated", {"response": response, "success": False})
            self.publish_event("plan.completed", {"plan": plan_to_dict(executed_plan), "success": False})
            return self.finish_result(
                RuntimeResult(
                    handled=True,
                    intent=intent,
                    permission=permission_decision,
                    plan=executed_plan,
                    tool=route.tool_name,
                    response=response,
                    tool_name=route.tool_name,
                    permission_status=permission_decision.status.value,
                    success=False,
                    error=tool_result.error,
                ),
                context=runtime_context,
                runtime_id=runtime_id,
                plan=executed_plan,
                started=started,
                detected_intent=intent.name,
                selected_tool=route.tool_name,
                permission_status=permission_decision.status.value,
                execution_result="failed",
                error_logs=[tool_result.error],
                metrics=plan_result["metrics"],
            )

        response = format_tool_output(tool_result.output)
        self.publish_runtime(execution_result="success", response=response)
        self.publish_event("response.generated", {"response": response, "success": True})
        self.publish_event("plan.completed", {"plan": plan_to_dict(executed_plan), "success": True})
        return self.finish_result(
            RuntimeResult(
                handled=True,
                intent=intent,
                permission=permission_decision,
                plan=executed_plan,
                tool=route.tool_name,
                response=response,
                tool_name=route.tool_name,
                permission_status=permission_decision.status.value,
                success=True,
                tool_output=tool_result.output,
            ),
            context=runtime_context,
            runtime_id=runtime_id,
            plan=executed_plan,
            started=started,
            detected_intent=intent.name,
            selected_tool=route.tool_name,
            permission_status=permission_decision.status.value,
            execution_result="success",
            metrics=plan_result["metrics"],
        )

    def handle(self, message, input_source="text"):
        """Backward-compatible runtime entrypoint."""
        return self.run(message, input_source=input_source)

    def create_context(self, text, input_source="text", **metadata):
        """Create a RuntimeContext for callers that do not import the class."""
        return RuntimeContext(
            text=text,
            source=input_source,
            language=metadata.get("language", ""),
            session_id=metadata.get("session_id", ""),
            user_id=metadata.get("user_id", ""),
            wake_word=metadata.get("wake_word", ""),
            conversation_id=metadata.get("conversation_id", ""),
            timestamp=metadata.get("timestamp", ""),
            current_date=metadata.get("current_date", ""),
            current_time=metadata.get("current_time", ""),
            timezone=metadata.get("timezone", ""),
        )

    def evaluate_intent_permission(self, intent, request):
        """Evaluate permission before selecting a concrete tool route."""
        subject = IntentPermissionSubject(permission_level=intent.permission_level)
        return self.tool_dispatcher.permission_layer.evaluate(subject, request)

    def execute_plan(self, plan, intent, started=None):
        """Execute plan steps sequentially through router and dispatcher."""
        execution_started = started or perf_counter()
        router_time = 0.0
        dispatcher_time = 0.0
        retry_count = 0

        if plan is None or len(plan.steps) == 0:
            return {
                "route": None,
                "tool_result": None,
                "plan": plan,
                "metrics": create_metrics(execution_started),
                "error": "Plan has no executable steps.",
            }

        final_route = None
        final_result = None
        current_plan = plan

        for index, step in enumerate(plan.steps):
            current_plan = update_plan_step_status(current_plan, index, STEP_STATUS_RUNNING)
            execution_context = ExecutionContext(
                plan=current_plan,
                step=step,
                retry_count=retry_count,
            )
            step_intent = create_step_intent(intent, step)
            route_started = perf_counter()
            route = resolve_tool_route(self.tool_router, step_intent)
            router_time += perf_counter() - route_started

            if route is None:
                current_plan = update_plan_step_status(current_plan, index, STEP_STATUS_FAILED)
                return {
                    "route": None,
                    "tool_result": None,
                    "plan": current_plan,
                    "metrics": create_metrics(
                        execution_started,
                        router_time=router_time,
                        dispatcher_time=dispatcher_time,
                        retry_count=retry_count,
                    ),
                    "error": f"No tool route found for plan step '{step.tool}'.",
                }

            self.publish_runtime(selected_tool=route.tool_name)
            dispatch_started = perf_counter()
            tool_result = self.tool_dispatcher.execute(
                ToolRequest(tool_name=route.tool_name, input_data=route.input_data)
            )
            dispatcher_time += perf_counter() - dispatch_started
            self.publish_event(
                "tool.executed",
                {
                    "tool": route.tool_name,
                    "success": tool_result.success,
                    "error": tool_result.error,
                    "retry_count": execution_context.retry_count,
                },
            )
            final_route = route
            final_result = tool_result

            if tool_result.success:
                current_plan = update_plan_step_status(current_plan, index, STEP_STATUS_COMPLETED)
            else:
                current_plan = update_plan_step_status(current_plan, index, STEP_STATUS_FAILED)
                if self.retry_policy.should_retry(retry_count):
                    retry_count += 1
                break

        return {
            "route": final_route,
            "tool_result": final_result,
            "plan": current_plan,
            "metrics": create_metrics(
                execution_started,
                router_time=router_time,
                dispatcher_time=dispatcher_time,
                retry_count=retry_count,
            ),
            "error": "",
        }

    def execute_parallel(self, plan):
        """Reserved parallel execution interface."""
        return execute_parallel(plan)

    def finish_result(
        self,
        result,
        context,
        runtime_id,
        started,
        plan=None,
        detected_intent="",
        selected_tool="",
        permission_status="",
        execution_result="",
        error_logs=None,
        metrics=None,
        fallback_used=False,
    ):
        """Attach diagnostics, elapsed time, and publish final runtime event."""
        elapsed = perf_counter() - started
        diagnostics = RuntimeDiagnostics(
            input_text=context.text,
            input_source=context.source,
            detected_intent=detected_intent,
            selected_tool=selected_tool,
            permission_status=permission_status,
            execution_result=execution_result,
            error_logs=tuple(error_logs or []),
            elapsed=elapsed,
            runtime_id=runtime_id,
            plan=plan,
            metrics=metrics,
            context=context,
        )
        status = calculate_result_status(result, execution_result)
        completed = RuntimeResult(
            handled=result.handled,
            intent=result.intent,
            permission=result.permission,
            plan=result.plan or plan,
            tool=result.tool or selected_tool,
            response=result.response,
            diagnostics=diagnostics,
            elapsed=elapsed,
            tool_name=result.tool_name or selected_tool,
            permission_status=result.permission_status or permission_status,
            success=result.success,
            error=result.error,
            status=status,
            execution_time=read_metric(metrics, "execution_time"),
            router_time=read_metric(metrics, "router_time"),
            dispatcher_time=read_metric(metrics, "dispatcher_time"),
            retry_count=read_metric(metrics, "retry_count"),
            fallback_used=fallback_used or read_metric(metrics, "fallback_used"),
            tool_output=result.tool_output,
        )
        self.publish_runtime(elapsed=elapsed)
        self.publish_completed(completed)
        self.publish_event(
            "runtime.finished",
            {
                "handled": completed.handled,
                "runtime_id": runtime_id,
                "success": completed.success,
                "status": completed.status,
                "elapsed": completed.elapsed,
                "intent": intent_to_dict(completed.intent),
                "plan": plan_to_dict(completed.plan),
                "tool": completed.tool,
                "error": completed.error,
                "metrics": metrics_to_dict(metrics),
            },
        )
        return completed

    def publish_tts_output(self, spoken):
        """Publish whether a handled intent reached TTS output."""
        value = "yes" if spoken else "no"
        self.publish_runtime(tts_output=value)

    def publish_runtime(
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
        """Publish intent runtime diagnostics when available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.publish_intent_runtime(
            input_text=input_text,
            input_source=input_source,
            detected_intent=detected_intent,
            selected_tool=selected_tool,
            permission_status=permission_status,
            execution_result=execution_result,
            response=response,
            tts_output=tts_output,
            error=error,
            elapsed=elapsed,
        )

    def publish_completed(self, result):
        """Publish one runtime completion event to the collector."""
        if self.diagnostics_collector is None:
            return

        if not hasattr(self.diagnostics_collector, "publish"):
            return

        self.diagnostics_collector.publish(
            "runtime.completed",
            {
                "handled": result.handled,
                "runtime_id": result.diagnostics.runtime_id,
                "success": result.success,
                "intent": intent_to_dict(result.intent),
                "plan": plan_to_dict(result.plan),
                "permission": result.permission_status,
                "tool": result.tool or result.tool_name,
                "response": result.response,
                "diagnostics": result.diagnostics.to_dict(),
                "elapsed": result.elapsed,
                "error": result.error,
                "metrics": metrics_to_dict(result.diagnostics.metrics),
            },
        )

    def publish_event(self, event_type, payload):
        """Publish one runtime event for diagnostics/history subscribers."""
        if self.diagnostics_collector is None:
            return

        if not hasattr(self.diagnostics_collector, "publish"):
            return

        self.diagnostics_collector.publish(event_type, payload)

    def log_event(self, message):
        """Publish one diagnostics event when available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def create_intent_candidate(tool, text, source):
    """Create one parsed intent candidate from tool metadata."""
    metadata = tool.metadata
    matched_prefix = find_matched_prefix(text, metadata.input_prefixes)
    confidence = score_metadata_match(metadata, normalize_text(text), matched_prefix)

    if metadata.input_mode == "arithmetic_expression" and is_arithmetic_expression(text):
        confidence = max(confidence, metadata.route_confidence)

    if confidence < metadata.route_confidence:
        return None

    parameters = build_input_data(metadata, text, matched_prefix)

    if parameters is None:
        return None

    return IntentCandidate(
        intent=Intent(
            name=select_intent_name(metadata),
            confidence=confidence,
            source=source,
            parameters=parameters,
            raw_text=text,
            tool_name=metadata.name,
            permission_level=metadata.permission_level,
        ),
        priority=metadata.priority,
    )


def select_intent_name(metadata):
    """Return the runtime intent name exposed in diagnostics."""
    if metadata.capability != "":
        return metadata.capability

    if len(metadata.supported_intents) > 0:
        return metadata.supported_intents[0]

    return metadata.name


def strip_wake_word(message):
    """Remove common Jarvis wake prefixes from user text."""
    text = str(message).strip()
    lowered = text.lower()
    prefixes = [
        "jarvis,",
        "jarvis",
        "\uc790\ube44\uc2a4,",
        "\uc790\ube44\uc2a4",
    ]

    for prefix in prefixes:
        if lowered == prefix:
            return ""

        if lowered.startswith(f"{prefix} "):
            return text[len(prefix):].strip()

    return text


def normalize_text(text):
    """Normalize text for metadata scoring."""
    return " ".join(str(text).strip().lower().rstrip("?").split())


def format_tool_output(output):
    """Format tool output for a spoken response."""
    if hasattr(output, "to_natural_language"):
        return output.to_natural_language()

    if isinstance(output, dict):
        return "\n".join([f"{key}: {value}" for key, value in output.items()])

    return str(output)


def normalize_runtime_context(context, input_source=None):
    """Return a RuntimeContext from new or legacy runtime inputs."""
    if isinstance(context, RuntimeContext):
        if input_source is None or input_source == context.source:
            return context

        return RuntimeContext(
            text=context.text,
            source=input_source,
            language=context.language,
            session_id=context.session_id,
            user_id=context.user_id,
            wake_word=context.wake_word,
            conversation_id=context.conversation_id,
            timestamp=context.timestamp,
            current_date=context.current_date,
            current_time=context.current_time,
            timezone=context.timezone,
        )

    return RuntimeContext(
        text=str(context),
        source=input_source or "text",
    )


def create_runtime_id():
    """Create a short runtime ID for diagnostics and replay."""
    return uuid4().hex[:6].upper()


def resolve_tool_route(tool_router, intent):
    """Resolve a tool route through the ToolRouter contract."""
    return tool_router.resolve(intent)


def intent_to_dict(intent):
    """Return a serializable intent payload."""
    if intent is None:
        return None

    return {
        "name": intent.name,
        "confidence": intent.confidence,
        "source": intent.source,
        "parameters": dict(intent.parameters),
        "raw_text": intent.raw_text,
        "tool_name": intent.tool_name,
        "permission_level": str(intent.permission_level),
    }


def create_step_intent(intent, step):
    """Create an intent-shaped object for one plan step."""
    return Intent(
        name=step.tool,
        confidence=intent.confidence,
        source=intent.source,
        parameters=dict(step.parameters),
        raw_text=intent.raw_text,
        tool_name=intent.tool_name,
        permission_level=intent.permission_level,
    )


def plan_to_dict(plan):
    """Return a serializable plan payload."""
    if plan is None:
        return None

    if hasattr(plan, "to_dict"):
        return plan.to_dict()

    return plan


def metrics_to_dict(metrics):
    """Return a serializable execution metrics payload."""
    if metrics is None:
        return None

    if hasattr(metrics, "to_dict"):
        return metrics.to_dict()

    return metrics


def read_metric(metrics, key):
    """Read one metric value with stable defaults."""
    if metrics is None:
        if key == "fallback_used":
            return False

        return 0

    return getattr(metrics, key, False if key == "fallback_used" else 0)


def format_runtime_error_response(error):
    """Return a user-facing runtime error without debug prefixes."""
    message = str(error or "").strip()

    if message == "":
        return "요청을 실행하지 못했습니다."

    if message.lower().startswith("tool failed:"):
        message = message.split(":", 1)[1].strip()

    return message


def calculate_result_status(result, execution_result):
    """Return a stable RuntimeResult execution status."""
    if getattr(result, "status", "") == EXECUTION_STATUS_CANCELLED:
        return EXECUTION_STATUS_CANCELLED

    if result.success:
        return EXECUTION_STATUS_COMPLETED

    if not result.handled and execution_result in ["", "empty_plan", "unmatched"]:
        return ""

    return EXECUTION_STATUS_FAILED
