from time import perf_counter

from jarvis.debug_trace import trace_event
from jarvis.core.events import InMemoryEventBus
from jarvis.permissions import PermissionLayer, PermissionStatus
from jarvis.runtime.planner import PlanResult, PlanStepResult, RuntimePlanner
from jarvis.runtime.task import TaskHistory, TaskRunner, TaskStateMachine
from jarvis.runtime.tool_dispatcher.context import DispatchContext
from jarvis.runtime.tool_dispatcher.registry import RuntimeToolRegistry
from jarvis.runtime.tool_dispatcher.result import DispatchResult, DispatchSelection
from jarvis.tools import ToolRequest, ToolResult
from jarvis.tools.router import select_candidate


class RuntimeToolDispatcher:
    """Select and execute native or external tools through one runtime facade."""

    def __init__(
        self,
        registry,
        permission_layer=None,
        diagnostics_collector=None,
        min_confidence=0.75,
        intent_parser=None,
        event_bus=None,
    ):
        """Create dispatcher from an existing registry."""
        self.registry = registry
        self.runtime_registry = RuntimeToolRegistry(registry)
        self.permission_layer = permission_layer or PermissionLayer(diagnostics_collector=diagnostics_collector)
        self.diagnostics_collector = diagnostics_collector
        self.min_confidence = float(min_confidence)
        self.intent_parser = intent_parser
        self.planner = RuntimePlanner(min_confidence=self.min_confidence, intent_parser=intent_parser)
        self.event_bus = event_bus or InMemoryEventBus()
        self.task_history = TaskHistory()
        self.task_runner = TaskRunner(
            execute_step=self.execute_task_step,
            resolve_step_input=self.resolve_step_input,
            format_response=format_tool_response,
            update_context=update_plan_context,
            merge_responses=merge_plan_responses,
            history=self.task_history,
            state_machine=TaskStateMachine(event_bus=self.event_bus),
        )

    def set_intent_parser(self, intent_parser):
        """Attach a structured intent parser to the runtime planner."""
        self.intent_parser = intent_parser
        self.planner = RuntimePlanner(min_confidence=self.min_confidence, intent_parser=intent_parser)

    def select(self, text, context=None):
        """Select the best tool for text without executing it."""
        context = context or DispatchContext(text=str(text or ""))
        candidates = self.find_candidates(text)

        if len(candidates) == 0:
            trace_event("dispatcher.selected", intent="unmatched", selected="", provider="", success=False, duration_ms=0)
            return None

        selected = candidates[0]
        trace_event(
            "dispatcher.selected",
            intent=selected.tool_name,
            selected=selected.tool_name,
            provider=selected.provider,
            success=True,
            duration_ms=0,
        )
        return selected

    def plan(self, text, context=None):
        """Prepare one or more tool selections without executing them."""
        plan = self.planner.plan(text, self.registry)
        selections = [
            DispatchSelection(
                tool_name=step.tool_name,
                confidence=1.0,
                input_data=dict(step.input_data),
                provider=getattr(self.registry.get(step.tool_name).metadata, "provider", "")
                if self.registry.get(step.tool_name) is not None
                else "",
                priority=getattr(self.registry.get(step.tool_name).metadata, "priority_label", "normal")
                if self.registry.get(step.tool_name) is not None
                else "normal",
                capability=getattr(self.registry.get(step.tool_name).metadata, "capability", "")
                if self.registry.get(step.tool_name) is not None
                else "",
            )
            for step in plan.steps
        ]

        if len(selections) == 0:
            for clause in split_multi_tool_text(text):
                selection = self.select(clause, context=context)

                if selection is not None:
                    selections.append(selection)

        return DispatchResult(
            success=len(selections) > 0,
            selected=selections[0] if selections else None,
            selections=selections,
            multi_tool_ready=len(selections) > 1,
        )

    def create_plan(self, text):
        """Create an ExecutionPlan without running it."""
        return self.planner.plan(text, self.registry)

    def execute_plan_text(self, text, confirmed=False):
        """Plan and execute text through ordered dispatcher steps."""
        return self.execute_plan(self.create_plan(text), confirmed=confirmed)

    def execute_plan(
        self,
        plan,
        confirmed=False,
        start_index=0,
        initial_context=None,
        pre_step_results=None,
        runtime_task=None,
    ):
        """Execute an ExecutionPlan sequentially."""
        if getattr(plan, "requires_clarification", False):
            return PlanResult(
                success=False,
                plan=plan,
                step_results=[],
                response=getattr(plan, "clarification_question", "") or "조금 더 구체적으로 말씀해 주세요.",
                error="requires_clarification",
            )

        if getattr(plan, "unsupported_reason", "") == "unsupported_conditional":
            return PlanResult(
                success=False,
                plan=plan,
                step_results=[],
                response="아직 조건부 알림은 지원하지 않습니다.",
                error="unsupported_conditional",
            )

        if getattr(plan, "intent_error", "") and len(plan.steps) == 0:
            return PlanResult(
                success=False,
                plan=plan,
                step_results=[],
                response="요청을 안전하게 해석하지 못했습니다.",
                error=getattr(plan, "intent_error", ""),
            )

        if confirmed and len(plan.steps) > 1:
            trace_event(
                "planner.resume_after_confirmation",
                plan_id=getattr(plan, "id", ""),
                step_count=plan.step_count,
            )

        return self.task_runner.run(
            plan,
            confirmed=confirmed,
            start_index=start_index,
            initial_context=initial_context,
            pre_step_results=pre_step_results,
            runtime_task=runtime_task,
        ).plan_result

    def execute_task_step(self, step, input_data, step_count, task_id=""):
        """Execute one task step through the existing dispatcher path."""
        trace_event(
            "planner.executing_step",
            plan_id=getattr(step, "plan_id", ""),
            task_id=task_id,
            step_index=step.index,
            step_count=step_count,
            tool=step.tool_name,
            action=step.action,
        )
        return self.execute(
            ToolRequest(tool_name=step.tool_name, input_data=input_data),
            step_index=step.index,
            step_count=step_count,
            task_id=task_id,
        )

    def resolve_step_input(self, step, context):
        """Fill a planned step input from prior step context when needed."""
        input_data = dict(step.input_data)

        if step.tool_name == "mail" and step.action == "send":
            contact = context.get("last_contact", {})
            calendar_event = context.get("last_calendar_event", {})
            calendar_mail = bool(input_data.pop("_workspace_calendar_mail", False))

            if contact and not input_data.get("to"):
                emails = tuple(contact.get("emails", ()) or ())
                if emails:
                    input_data["to"] = [emails[0]]
                    input_data["recipient"] = emails[0]
                    input_data["recipient_name"] = contact.get("display_name", "")

            if calendar_mail and calendar_event:
                title = calendar_event.get("title", "") or "일정"
                date_text = calendar_event.get("date", "")
                time_text = calendar_event.get("time", "")
                when = " ".join(part for part in [date_text, time_text] if part)
                input_data["subject"] = f"{title} 일정 안내"
                input_data["body"] = f"{when} {title} 일정입니다.".strip()
            elif calendar_mail:
                input_data["subject"] = "일정 안내"

            return input_data

        if step.tool_name != "reminder":
            return input_data

        if input_data.get("datetime", ""):
            return input_data

        calendar_event = context.get("last_calendar_event", {})

        if len(calendar_event) == 0:
            return input_data

        event_time = calendar_event.get("time", "") or "00:00"

        if len(event_time.split(":")) == 2:
            event_time = f"{event_time}:00"

        input_data["title"] = input_data.get("title") or calendar_event.get("title", "")
        input_data["datetime"] = f"{calendar_event.get('date', '')}T{event_time}"
        return input_data

    def execute_text(self, text, context=None):
        """Select and execute the best tool for free text."""
        started = perf_counter()
        selection = self.select(text, context=context)

        if selection is None:
            return DispatchResult(success=False, error="No matching tool.", duration_ms=elapsed_ms(started))

        tool_result = self.execute(ToolRequest(tool_name=selection.tool_name, input_data=selection.input_data))
        return DispatchResult(
            success=tool_result.success,
            selected=selection,
            tool_result=tool_result,
            response=getattr(tool_result, "output", ""),
            error=tool_result.error,
            duration_ms=elapsed_ms(started),
        )

    def execute(self, request, step_index=0, step_count=0, task_id=""):
        """Execute one ToolRequest and return a ToolResult-compatible result."""
        started = perf_counter()
        tool_request = normalize_request(request)
        tool = self.registry.get(tool_request.tool_name)

        if tool is None:
            duration = elapsed_ms(started)
            trace_event(
                "dispatcher.result",
                intent=tool_request.tool_name,
                selected=tool_request.tool_name,
                provider="",
                success=False,
                duration_ms=duration,
                step_index=step_index,
                step_count=step_count,
                task_id=task_id,
            )
            return ToolResult(
                tool_name=tool_request.tool_name,
                success=False,
                error=f"Tool '{tool_request.tool_name}' is not registered.",
            )

        permission_decision = self.permission_layer.evaluate(tool, tool_request)

        if not permission_decision.allowed:
            duration = elapsed_ms(started)
            trace_event(
                "dispatcher.result",
                intent=tool_request.tool_name,
                selected=tool_request.tool_name,
                provider=getattr(tool.metadata, "provider", ""),
                success=False,
                duration_ms=duration,
                step_index=step_index,
                step_count=step_count,
                task_id=task_id,
            )
            return create_permission_tool_result(tool_request, permission_decision)

        try:
            result = tool.execute(tool_request.input_data)
        except Exception as error:
            duration = elapsed_ms(started)
            trace_event(
                "dispatcher.result",
                intent=tool_request.tool_name,
                selected=tool_request.tool_name,
                provider=getattr(tool.metadata, "provider", ""),
                success=False,
                duration_ms=duration,
                step_index=step_index,
                step_count=step_count,
                task_id=task_id,
            )
            return ToolResult(tool_name=tool_request.tool_name, success=False, error=str(error))

        duration = elapsed_ms(started)
        trace_event(
            "dispatcher.result",
            intent=tool_request.tool_name,
            selected=tool_request.tool_name,
            provider=getattr(tool.metadata, "provider", ""),
            success=result.success,
            duration_ms=duration,
            step_index=step_index,
            step_count=step_count,
            task_id=task_id,
        )
        return result

    def find_candidates(self, text):
        """Return sorted dispatcher selections for text."""
        candidates = []

        for tool in self.runtime_registry.list():
            if tool.metadata.deprecated:
                continue

            candidate = select_candidate(tool, str(text or ""))

            if candidate is None:
                continue

            if candidate["confidence"] < self.min_confidence:
                continue

            candidates.append(
                DispatchSelection(
                    tool_name=tool.metadata.name,
                    confidence=candidate["confidence"],
                    input_data=dict(candidate["input_data"]),
                    provider=getattr(tool.metadata, "provider", ""),
                    priority=getattr(tool.metadata, "priority_label", "normal"),
                    capability=getattr(tool.metadata, "capability", ""),
                )
            )

        return sorted(candidates, key=lambda item: (item.confidence, priority_to_int(item.priority), item.tool_name), reverse=True)


def normalize_request(request):
    """Return ToolRequest."""
    if isinstance(request, ToolRequest):
        return request

    return ToolRequest(tool_name=str(request), input_data={})


def create_permission_tool_result(tool_request, permission_decision):
    """Create ToolResult for permission failures."""
    if permission_decision.status == PermissionStatus.CONFIRM_REQUIRED:
        return ToolResult(
            tool_name=tool_request.tool_name,
            success=False,
            error=f"Permission confirmation required: {permission_decision.reason}",
        )

    return ToolResult(
        tool_name=tool_request.tool_name,
        success=False,
        error=f"Permission denied: {permission_decision.reason}",
    )


def priority_to_int(priority):
    """Return sortable priority value."""
    normalized = str(priority or "normal").lower()

    if normalized == "high":
        return 100

    if normalized == "low":
        return -100

    return 0


def split_multi_tool_text(text):
    """Split simple multi-tool requests for future execution."""
    normalized = str(text or "").strip()

    if normalized == "":
        return []

    clauses = [normalized]

    for separator in [" 알려주고 ", " 알려줘 그리고 ", " 그리고 ", " 또 "]:
        if separator in normalized:
            clauses = [part.strip() for part in normalized.split(separator) if part.strip()]
            break

    return clauses


def format_tool_response(tool_result):
    """Return natural language for one ToolResult."""
    output = getattr(tool_result, "output", None)
    data = getattr(output, "data", None)

    if hasattr(data, "to_natural_language"):
        return data.to_natural_language()

    if hasattr(output, "to_natural_language"):
        return output.to_natural_language()

    if output is not None:
        return str(output)

    return getattr(tool_result, "error", "")


def update_plan_context(context, step, tool_result):
    """Update execution context from one completed step."""
    if not getattr(tool_result, "success", False):
        return

    output = getattr(tool_result, "output", None)
    data = getattr(output, "data", None)

    if step.tool_name == "contacts":
        contact = getattr(data, "contact", None)
        if contact is not None:
            context["last_contact"] = {
                "display_name": getattr(contact, "display_name", ""),
                "emails": tuple(getattr(contact, "emails", ()) or ()),
                "id": getattr(contact, "id", ""),
            }
        return

    if step.tool_name != "calendar":
        return

    events = list(getattr(data, "events", []) or [])

    if len(events) == 0:
        return

    requested_time = str(getattr(step, "input_data", {}).get("time", "") or "")
    event = next((item for item in events if requested_time and getattr(item, "time", "") == requested_time), events[0])
    context["last_calendar_event"] = {
        "title": getattr(event, "title", ""),
        "date": getattr(event, "date", ""),
        "time": getattr(event, "time", ""),
        "id": getattr(event, "id", ""),
    }


def merge_plan_responses(step_results, plan=None):
    """Merge multiple Ability responses into one concise response."""
    successful_tools = [result.tool_name for result in step_results if result.success]

    if "calendar" in successful_tools and "reminder" in successful_tools:
        remind_before = find_remind_before(plan)

        if remind_before > 0:
            return f"일정을 등록했고, {remind_before}분 전 알림도 등록했습니다."

        return "일정을 등록했고, 알림도 등록했습니다."

    responses = [result.response for result in step_results if result.response]
    return "\n".join(dict.fromkeys(responses))


def find_remind_before(plan):
    """Return the first reminder step's remind_before value."""
    if plan is None:
        return 0

    for step in getattr(plan, "steps", []):
        if step.tool_name == "reminder":
            try:
                return int(step.input_data.get("remind_before", 0))
            except (TypeError, ValueError):
                return 0

    return 0


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)
