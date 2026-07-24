import os
import re
from dataclasses import replace
from datetime import datetime, timedelta

from jarvis.debug_trace import trace_event
from jarvis.runtime.intent import IntentContext
from jarvis.runtime.planner.plan import ExecutionPlan
from jarvis.runtime.planner.step import ExecutionStep
from jarvis.tools.router import select_candidate


class RuntimePlanner:
    """Rule-based multi-tool planner for runtime text."""

    def __init__(self, min_confidence=0.75, intent_parser=None):
        """Create planner."""
        self.min_confidence = float(min_confidence)
        self.intent_parser = intent_parser

    def plan(self, text, registry):
        """Return an ExecutionPlan without executing it."""
        raw_text = str(text or "").strip()
        trace_event("planner.parse", raw_text=raw_text)

        if raw_text == "" or registry is None:
            return ExecutionPlan(raw_text=raw_text)

        if is_unsupported_conditional(raw_text):
            plan = ExecutionPlan(raw_text=raw_text, unsupported_reason="unsupported_conditional")
            trace_plan(plan)
            return plan

        if is_unsupported_second_reminder(raw_text):
            plan = ExecutionPlan(
                raw_text=raw_text,
                requires_clarification=True,
                clarification_question="초 단위 알림은 아직 안정적으로 지원하지 않습니다. 몇 분 뒤로 알려드릴까요?",
            )
            trace_plan(plan)
            return plan

        if is_probable_unresolved_reminder(raw_text):
            plan = ExecutionPlan(
                raw_text=raw_text,
                requires_clarification=True,
                clarification_question="몇 분 뒤에 알려드릴까요?",
            )
            trace_plan(plan)
            return plan

        workspace_plan = create_workspace_integration_plan(raw_text, registry)

        if workspace_plan is not None:
            trace_intent_resolve(workspace_plan, "workspace_rule")
            trace_plan(workspace_plan)
            return workspace_plan

        trace_intent_rule_candidates(raw_text, registry)

        if self.intent_parser is not None and should_force_intent_parser():
            intent_plan = self.create_intent_plan(raw_text, registry)
            trace_intent_ai_plan(intent_plan)

            if intent_plan is not None and (intent_plan.step_count > 0 or intent_plan.requires_clarification or intent_plan.unsupported_reason or intent_plan.intent_error):
                trace_intent_resolve(intent_plan, "ai_forced")
                trace_plan(intent_plan)
                return intent_plan

        if (
            self.intent_parser is not None
            and should_intent_parser_run_first(raw_text)
            and not is_calendar_reminder_rule_candidate(raw_text)
        ):
            intent_plan = self.create_intent_plan(raw_text, registry)
            trace_intent_ai_plan(intent_plan)

            if intent_plan is not None:
                trace_intent_resolve(intent_plan, "ai_before_rule")
                trace_plan(intent_plan)
                return intent_plan

        clauses = split_plan_clauses(raw_text)

        if len(clauses) == 1 and is_calendar_reminder_rule_candidate(raw_text):
            clauses = split_calendar_reminder_clause(raw_text)

        steps = []

        for clause in clauses:
            step = self.create_step(clause, registry, steps)

            if step is not None:
                steps.append(step)

        steps = attach_calendar_reminder_overrides(steps)
        plan = ExecutionPlan(raw_text=raw_text, steps=tuple(steps))

        if plan.step_count == 0 and self.intent_parser is not None:
            intent_plan = self.create_intent_plan(raw_text, registry)
            trace_intent_ai_plan(intent_plan)

            if intent_plan is not None:
                trace_intent_resolve(intent_plan, "rule_failed_ai_fallback")
                trace_plan(intent_plan)
                return intent_plan

        if plan.step_count == 0 and is_probable_unresolved_reminder(raw_text):
            plan = ExecutionPlan(
                raw_text=raw_text,
                requires_clarification=True,
                clarification_question="紐?遺??ㅼ뿉 ?뚮젮?쒕┫源뚯슂?",
            )
            trace_plan(plan)
            return plan

        trace_plan(plan)
        trace_intent_resolve(plan, "rule_plan")
        return plan

    def create_intent_plan(self, text, registry):
        """Create a plan from the structured Intent Parser."""
        context = create_intent_context(registry)
        result = self.intent_parser.parse(text, context)

        if result.unsupported_reason:
            return ExecutionPlan(raw_text=text, unsupported_reason=result.unsupported_reason, intent_error=result.error_code)

        if result.requires_clarification:
            return ExecutionPlan(
                raw_text=text,
                requires_clarification=True,
                clarification_question=result.clarification_question,
                intent_error=result.error_code,
            )

        if not result.success:
            if result.error_code:
                return ExecutionPlan(raw_text=text, intent_error=result.error_code)

            return None

        steps = []

        for intent in result.intents:
            step = execution_step_from_intent(intent, len(steps) + 1, context)

            if step is not None:
                steps.append(step)

        steps = attach_calendar_reminder_overrides(steps)
        return ExecutionPlan(raw_text=text, steps=tuple(steps))

    def create_step(self, clause, registry, previous_steps):
        """Create a single ExecutionStep for a clause."""
        normalized = normalize_clause(clause)

        if normalized == "":
            return None

        if is_calendar_list_command(normalized):
            selection = select_best_tool(registry, normalized, self.min_confidence, preferred_tool="calendar")

            if selection is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name=selection["tool"].metadata.name,
                    action="list",
                    input_data=dict(selection["input_data"]),
                    raw_text=normalized,
                )

            calendar_tool = registry.get("calendar")

            if calendar_tool is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name="calendar",
                    action="list",
                    input_data={"text": normalized},
                    raw_text=normalized,
                )

        if is_calendar_create_command(normalized):
            selection = select_best_tool(registry, normalized, self.min_confidence, preferred_tool="calendar")

            if selection is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name=selection["tool"].metadata.name,
                    action="create",
                    input_data=dict(selection["input_data"]),
                    raw_text=normalized,
                )

            calendar_tool = registry.get("calendar")

            if calendar_tool is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name="calendar",
                    action="create",
                    input_data={"text": normalized},
                    raw_text=normalized,
                )

        mail_text = corrected_mail_stt_variant(normalized)
        if is_mail_command(normalized):
            selection = select_best_tool(registry, mail_text, self.min_confidence, preferred_tool="mail")

            if selection is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name=selection["tool"].metadata.name,
                    action=infer_action("mail", mail_text),
                    input_data=dict(selection["input_data"]),
                    raw_text=normalized,
                )

        if is_contact_command(normalized):
            selection = select_best_tool(registry, normalized, self.min_confidence, preferred_tool="contacts")

            if selection is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name=selection["tool"].metadata.name,
                    action=infer_action("contacts", normalized),
                    input_data=dict(selection["input_data"]),
                    raw_text=normalized,
                )

        if is_todo_command(normalized):
            selection = select_best_tool(registry, normalized, self.min_confidence, preferred_tool="todo")

            if selection is not None:
                return ExecutionStep(
                    index=len(previous_steps) + 1,
                    tool_name=selection["tool"].metadata.name,
                    action=infer_action("todo", normalized),
                    input_data=dict(selection["input_data"]),
                    raw_text=normalized,
                )

        reminder_follow_up = parse_reminder_follow_up(normalized)

        if reminder_follow_up is not None and has_previous_tool(previous_steps, "calendar"):
            return ExecutionStep(
                index=len(previous_steps) + 1,
                tool_name="reminder",
                action="create",
                input_data=reminder_follow_up,
                raw_text=normalized,
                depends_on=(last_tool_index(previous_steps, "calendar"),),
            )

        selection = select_best_tool(registry, normalized, self.min_confidence)

        if selection is None:
            selection = create_rule_fallback_selection(registry, normalized)

        if selection is None:
            return None

        return ExecutionStep(
            index=len(previous_steps) + 1,
            tool_name=selection["tool"].metadata.name,
            action=infer_action(selection["tool"].metadata.name, normalized),
            input_data=dict(selection["input_data"]),
            raw_text=normalized,
        )

    def create_condition_steps(self, text, registry):
        """Create a simple condition plan such as weather followed by reminder."""
        normalized = normalize_clause(text)

        if "비" not in normalized or not contains_reminder_command(normalized):
            return []

        steps = []
        weather = select_best_tool(registry, normalized, self.min_confidence, preferred_tool="weather")

        if weather is not None:
            steps.append(
                ExecutionStep(
                    index=1,
                    tool_name="weather",
                    action="query",
                    input_data=dict(weather["input_data"]),
                    raw_text=normalized,
                )
            )

        reminder = select_best_tool(registry, normalized, self.min_confidence, preferred_tool="reminder")

        if reminder is not None:
            steps.append(
                ExecutionStep(
                    index=len(steps) + 1,
                    tool_name="reminder",
                    action="create",
                    input_data=dict(reminder["input_data"]),
                    raw_text=normalized,
                )
            )

        return steps


def select_best_tool(registry, text, min_confidence, preferred_tool=""):
    """Return the highest scoring router candidate."""
    candidates = []

    for tool in registry.list():
        if tool.metadata.deprecated:
            continue

        if preferred_tool and tool.metadata.name != preferred_tool:
            continue

        candidate = select_candidate(tool, text)

        if candidate is None or candidate["confidence"] < min_confidence:
            continue

        candidates.append(candidate)

    if len(candidates) == 0:
        if preferred_tool:
            return None

        return create_rule_fallback_selection(registry, text)

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate["confidence"],
            getattr(candidate["tool"].metadata, "priority", 0),
            candidate["tool"].metadata.name,
        ),
        reverse=True,
    )[0]


def create_rule_fallback_selection(registry, text):
    """Return a low-level rule fallback for short common intents."""
    if is_weather_query_command(text):
        tool = registry.get("weather")

        if tool is not None:
            return {"tool": tool, "confidence": 0.8, "input_data": {"text": text}}

    if is_calendar_create_command(text):
        tool = registry.get("calendar")

        if tool is not None:
            return {"tool": tool, "confidence": 0.86, "input_data": {"text": text}}

    if is_contact_command(text):
        tool = registry.get("contacts")

        if tool is not None:
            return {"tool": tool, "confidence": 0.9, "input_data": {"text": text}}

    if is_mail_command(text):
        tool = registry.get("mail")

        if tool is not None:
            return {"tool": tool, "confidence": 0.9, "input_data": {"text": text}}

    if is_todo_command(text):
        tool = registry.get("todo")

        if tool is not None:
            return {"tool": tool, "confidence": 0.9, "input_data": {"text": text}}

    if is_standalone_reminder_create_command(text):
        tool = registry.get("reminder")

        if tool is not None:
            return {"tool": tool, "confidence": 0.8, "input_data": {"text": text}}

    return None


def trace_intent_rule_candidates(text, registry):
    """Emit rule candidates before Planner picks a route."""
    candidates = collect_rule_candidates(text, registry)
    candidate_text = ",".join(f"{item['ability']}.{item['action']}:{item['score']:.2f}" for item in candidates) or "-"
    trace_event("intent_rule.candidates", candidates=candidate_text)


def collect_rule_candidates(text, registry):
    """Return diagnostics-only rule candidates for intent resolution."""
    normalized = normalize_clause(text)
    candidates = []

    if is_calendar_reminder_rule_candidate(normalized):
        candidates.append({"ability": "calendar", "action": "create", "score": 0.92})
        candidates.append({"ability": "reminder", "action": "modifier", "score": 0.9})

    if registry is not None:
        for tool in registry.list():
            if tool.metadata.deprecated:
                continue

            candidate = select_candidate(tool, normalized)

            if candidate is None:
                continue

            candidates.append(
                {
                    "ability": tool.metadata.name,
                    "action": infer_action(tool.metadata.name, normalized),
                    "score": float(candidate.get("confidence", 0.0)),
                }
            )

    if is_calendar_create_command(normalized):
        candidates.append({"ability": "calendar", "action": "create", "score": 0.86})

    if is_weather_query_command(normalized):
        candidates.append({"ability": "weather", "action": "query", "score": 0.86})

    if is_standalone_reminder_create_command(normalized):
        candidates.append({"ability": "reminder", "action": "create", "score": 0.8})

    if is_mail_command(normalized):
        candidates.append({"ability": "mail", "action": infer_action("mail", normalized), "score": 0.88})

    ranked = {}

    for candidate in candidates:
        key = (candidate["ability"], candidate["action"])
        previous = ranked.get(key)

        if previous is None or candidate["score"] > previous["score"]:
            ranked[key] = candidate

    return sorted(ranked.values(), key=lambda candidate: candidate["score"], reverse=True)


def trace_intent_ai_plan(plan):
    """Emit a compact AI intent candidate summary from a produced plan."""
    if plan is None:
        trace_event("intent_ai.result", result="-", step_count=0)
        return

    result = ",".join(f"{step.tool_name}.{step.action or '-'}" for step in plan.steps) or "-"
    trace_event(
        "intent_ai.result",
        result=result,
        step_count=plan.step_count,
        requires_clarification=plan.requires_clarification,
        intent_error=plan.intent_error,
    )


def trace_intent_resolve(plan, reason):
    """Emit the final intent route chosen by the planner."""
    if plan is None:
        trace_event("intent_resolve.selected", selected="-", reason=reason)
        return

    selected = ",".join(f"{step.tool_name}.{step.action or '-'}" for step in plan.steps) or "-"
    trace_event(
        "intent_resolve.selected",
        selected=selected,
        reason=reason,
        step_count=plan.step_count,
        requires_clarification=plan.requires_clarification,
    )


def trace_plan(plan):
    """Emit planner trace events for one plan."""
    for step in plan.steps:
        trace_event(
            "planner.step",
            step_index=step.index,
            step_count=plan.step_count,
            tool=step.tool_name,
            action=step.action,
        )

    trace_event(
        "planner.completed",
        step_count=plan.step_count,
        success=plan.step_count > 0 and not bool(getattr(plan, "unsupported_reason", "")),
        unsupported_reason=getattr(plan, "unsupported_reason", ""),
    )


def is_unsupported_conditional(text):
    """Return whether text asks for unsupported conditional execution."""
    normalized = normalize_clause(text)
    return "면" in normalized and ("비" in normalized or "오면" in normalized) and contains_reminder_command(normalized)


def is_unsupported_second_reminder(text):
    """Return whether text asks for an unsupported seconds-based reminder."""
    normalized = str(text or "")
    has_seconds = bool(re.search(r"\d+\s*초", normalized))
    has_reminder = any(token in normalized for token in ["알려", "알림", "챙겨", "깨워", "해 줘", "해줘"])
    return has_seconds and has_reminder


def split_plan_clauses(text):
    """Split user text into ordered planning clauses."""
    normalized = " ".join(str(text or "").strip().split())

    if normalized == "":
        return []

    parts = re.split(r"\s*(?:그리고|다음으로)\s*", normalized)
    clauses = []

    for part in parts:
        clauses.extend(split_attached_and(part))

    return [clause for clause in clauses if clause]


def create_workspace_integration_plan(text, registry):
    """Build deterministic Contacts/Calendar -> Gmail plans."""
    normalized = normalize_clause(text)

    if registry is None or registry.get("mail") is None:
        return None

    contact_match = re.fullmatch(
        r"(?P<name>.+?)\s*연락처\s*(?:찾아서|찾아\s*서|찾고)\s*(?P<tail>.*(?:메일|이메일)\s*(?:보내줘|보내\s*줘|보내|전송해줘|전송해))",
        normalized,
    )
    if contact_match and registry.get("contacts") is not None:
        name = contact_match.group("name").strip()
        tail = contact_match.group("tail").strip()
        mail_text = tail if re.match(r"^.+?(?:에게|한테|으로|로)\s+", tail) else f"{name}에게 {tail}"
        return ExecutionPlan(
            raw_text=normalized,
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="contacts",
                    action="get",
                    input_data={"text": f"{name} 이메일 알려줘"},
                    raw_text=f"{name} 연락처 찾아줘",
                ),
                ExecutionStep(
                    index=2,
                    tool_name="mail",
                    action="send",
                    input_data={"action": "send", "raw_text": mail_text},
                    raw_text=mail_text,
                    depends_on=(1,),
                ),
            ),
        )

    calendar_match = re.fullmatch(
        r"(?P<name>.+?)(?:에게|한테)\s+(?P<schedule>.+?\s+일정)\s*(?:을|를)?\s*(?:메일|이메일)?로?\s*(?:보내줘|보내\s*줘|보내|전송해줘|전송해)",
        normalized,
    )
    if calendar_match and registry.get("calendar") is not None:
        name = calendar_match.group("name").strip()
        schedule = calendar_match.group("schedule").strip()
        return ExecutionPlan(
            raw_text=normalized,
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="calendar",
                    action="list",
                    input_data={"text": f"{schedule} 알려줘"},
                    raw_text=f"{schedule} 알려줘",
                ),
                ExecutionStep(
                    index=2,
                    tool_name="mail",
                    action="send",
                    input_data={
                        "action": "send",
                        "recipient": name,
                        "recipient_name": name,
                        "raw_text": "",
                        "_workspace_calendar_mail": True,
                    },
                    raw_text=normalized,
                    depends_on=(1,),
                ),
            ),
        )

    return None


def split_calendar_reminder_clause(text):
    """Split a calendar event command from an attached relative reminder modifier."""
    normalized = normalize_clause(text)
    reminder_clause = extract_relative_reminder_clause(normalized)

    if reminder_clause == "":
        return [normalized]

    calendar_clause = remove_relative_reminder_clause(normalized)
    calendar_clause = normalize_calendar_create_clause(calendar_clause)

    return [calendar_clause, reminder_clause]


def extract_relative_reminder_clause(text):
    """Return a reminder modifier such as '1시간 전 알려줘' from text."""
    normalized = str(text or "")
    pattern = r"((?:\d+|한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉|열)\s*(?:분|시간)\s*전(?:에)?\s*(?:알려\s*줘|알려줘|알려|알림|알람|깨워\s*줘|깨워줘).*)$"
    match = re.search(pattern, normalized)

    if not match:
        return ""

    return normalize_clause(match.group(1))


def remove_relative_reminder_clause(text):
    """Remove a trailing relative reminder modifier from a calendar command."""
    normalized = str(text or "")
    reminder_clause = extract_relative_reminder_clause(normalized)

    if reminder_clause:
        normalized = normalized[: -len(reminder_clause)].strip()

    normalized = re.sub(r"\s*(그리고|하고|해\s*주고|해주고|주고|넣고|넣어\s*주고|넣어주고)\s*$", " ", normalized)
    normalized = re.sub(r"\s*(알람|알림|리마인더)\s*도?\s*$", " ", normalized)
    return normalize_clause(normalized)


def normalize_calendar_create_clause(text):
    """Make a calendar-like clause explicit enough for Calendar routing."""
    normalized = normalize_clause(text)

    if not has_calendar_event_signal(normalized):
        return normalized

    if not is_calendar_create_command(normalized):
        normalized = f"{normalized} 일정 등록"

    return normalize_clause(normalized)


def split_attached_and(text):
    """Split Korean attached connector forms such as '등록하고'."""
    value = str(text or "").strip()

    if value == "":
        return []

    match = re.search(
        r"(.+?)(등록하고|등록해주고|등록해 주고|추가하고|추가해주고|추가해 주고|잡고|잡아주고|잡아 주고|넣고|넣어주고|넣어 주고|알려주고|알려 줘고)\s+(.+)",
        value,
    )

    if not match:
        return [value]

    first = (match.group(1) + match.group(2)).strip()
    connector = match.group(2)
    if connector in {"등록하고", "등록해주고", "등록해 주고", "추가하고", "추가해주고", "추가해 주고"}:
        first = re.sub(r"하고$", "", first)
        first = re.sub(r"해\s*주고$", "해 줘", first)
    elif connector in {"잡고", "잡아주고", "잡아 주고"}:
        first = re.sub(r"잡고$", "잡아 줘", first)
        first = re.sub(r"잡아\s*주고$", "잡아 줘", first)
    elif connector in {"넣고", "넣어주고", "넣어 주고"}:
        if any(token in first for token in ["일정", "약속", "예약", "만나기", "회의"]):
            first = re.sub(r"(알람|알림|리마인더)\s*도?\s*넣(?:어\s*주)?고$", "일정 등록해 줘", first)
            first = re.sub(r"넣고$", "넣어 줘", first)
            first = re.sub(r"넣어\s*주고$", "넣어 줘", first)
        else:
            first = re.sub(r"넣고$", "넣어 줘", first)
            first = re.sub(r"넣어\s*주고$", "넣어 줘", first)
    elif connector in {"알려주고", "알려 줘고"}:
        first = re.sub(r"알려\s*주고$", "알려줘", first)

    second = match.group(3).strip()
    return [first.strip(), second]






def normalize_clause(clause):
    """Normalize one clause after connector splitting."""
    text = " ".join(str(clause or "").strip().split())
    return text.strip(" .?!")


KOREAN_NUMBER_WORDS = {
    "\ud55c": 1,
    "\ud558\ub098": 1,
    "\ub450": 2,
    "\ub458": 2,
    "\uc138": 3,
    "\uc14b": 3,
    "\ub124": 4,
    "\ub137": 4,
    "\ub2e4\uc12f": 5,
    "\uc5ec\uc12f": 6,
    "\uc77c\uacf1": 7,
    "\uc5ec\ub35f": 8,
    "\uc544\ud649": 9,
    "\uc5f4": 10,
}


def parse_korean_number_word(value):
    """Return integer for a small Korean native number word."""
    return KOREAN_NUMBER_WORDS.get(str(value or "").strip())


def parse_relative_reminder_minutes(text):
    """Return minutes for relative reminder phrases such as '1 hour before'."""
    normalized = str(text or "")

    day_match = re.search(r"(\d+)\s*\uc77c\s*\uc804", normalized)
    if day_match:
        return int(day_match.group(1)) * 1440

    if any(token in normalized for token in ["\ud558\ub8e8 \uc804", "\ud558\ub8e8\uc804\uc5d0", "\ud558\ub8e8 \uc804\uc5d0"]):
        return 1440

    hour_match = re.search(r"(\d+)\s*\uc2dc\uac04\s*\uc804", normalized)
    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*\ubd84\s*\uc804", normalized)
    if minute_match:
        return int(minute_match.group(1))

    word_pattern = "|".join(re.escape(word) for word in sorted(KOREAN_NUMBER_WORDS, key=len, reverse=True))

    word_hour_match = re.search(rf"({word_pattern})\s*\uc2dc\uac04\s*\uc804", normalized)
    if word_hour_match:
        return parse_korean_number_word(word_hour_match.group(1)) * 60

    word_minute_match = re.search(rf"({word_pattern})\s*\ubd84\s*\uc804", normalized)
    if word_minute_match:
        return parse_korean_number_word(word_minute_match.group(1))

    return None


def parse_reminder_follow_up(text):
    """Return Reminder input data for a calendar-relative reminder clause."""
    if not contains_reminder_command(text):
        return None

    remind_before = parse_relative_reminder_minutes(text)

    if remind_before is None:
        return None

    return {
        "action": "create",
        "title": "",
        "datetime": "",
        "remind_before": remind_before,
        "remind_before_minutes": remind_before,
        "raw_text": text,
    }


def attach_calendar_reminder_overrides(steps):
    """Copy calendar-relative reminder offsets onto their source calendar step."""
    if not steps:
        return steps

    calendar_updates = {}

    for step in steps:
        if step.tool_name != "reminder":
            continue

        remind_before = read_step_remind_before_minutes(step.input_data)

        if remind_before is None:
            continue

        for dependency in step.depends_on:
            dependent_index = int(dependency or 0)

            if dependent_index > 0:
                calendar_updates[dependent_index] = remind_before

    if not calendar_updates:
        return steps

    patched = []

    for step in steps:
        if step.tool_name == "calendar" and step.index in calendar_updates:
            input_data = dict(step.input_data)
            input_data["remind_before_minutes"] = calendar_updates[step.index]
            patched.append(replace(step, input_data=input_data))
        else:
            patched.append(step)

    return patched


def read_step_remind_before_minutes(input_data):
    """Return an integer reminder offset from planner step data."""
    for key in ["remind_before_minutes", "remind_before"]:
        if key not in input_data:
            continue

        try:
            return int(input_data.get(key))
        except (TypeError, ValueError):
            return None

    return None


def contains_reminder_command(text):
    """Return whether text asks to notify the user."""
    return any(token in text for token in ["알려줘", "알려 줘", "알림", "알람", "챙기라고", "하라고"])


def is_standalone_reminder_create_command(text):
    """Return whether text should create a standalone reminder without another ability."""
    normalized = str(text or "")

    explicit_reminder = any(token in normalized for token in ["알림", "알람", "리마인더", "깨워", "챙겨", "챙기"])
    timed_reminder = contains_reminder_command(normalized) and (
        has_relative_reminder_signal(normalized)
        or bool(re.search(r"\d+\s*(?:분|시간|초|시)", normalized))
        or any(token in normalized for token in ["내일", "오늘", "모레", "아침", "점심", "저녁", "오전", "오후"])
    )

    return explicit_reminder or timed_reminder


def is_calendar_list_command(text):
    """Return whether a list command should route to Calendar before Reminder."""
    normalized = str(text or "")
    calendar_subject = any(
        token in normalized
        for token in [
            "\uc77c\uc815",
            "\uc77c\uc815\uc744",
            "\uc77c\uc815\uc740",
            "\uc77c\uc815\uc774",
            "\uc77c\uc815\uc774\ub098",
            "\uc57d\uc18d",
            "\uc608\uc57d",
        ]
    )
    list_verb = any(
        token in normalized
        for token in [
            "\uc54c\ub824",
            "\ubcf4\uc5ec",
            "\uc870\ud68c",
            "\ubcf4\uace0",
            "\uc788",
            "\ubb50",
        ]
    )
    create_or_mutate = any(
        token in normalized
        for token in [
            "\ub4f1\ub85d",
            "\ucd94\uac00",
            "\uc7a1\uc544",
            "\uc7a1\uc544\uc918",
            "\uc0ad\uc81c",
            "\uc9c0\uc6cc",
            "\ubc14\uafd4",
            "\ubcc0\uacbd",
        ]
    )

    return calendar_subject and list_verb and not create_or_mutate

def is_calendar_create_command(text):
    """Return whether a create command should route to Calendar before Reminder."""
    normalized = str(text or "")
    calendar_subject = any(token in normalized for token in ["일정", "약속", "예약", "만나기", "회의"])
    create_verb = any(token in normalized for token in ["등록", "추가", "잡아", "잡고", "넣어", "만들어"])
    explicit_reminder = any(token in normalized for token in ["알림", "알람", "리마인더"])

    if explicit_reminder and not calendar_subject:
        return False

    return calendar_subject and create_verb


def is_weather_query_command(text):
    """Return whether text asks for weather or rain information."""
    normalized = str(text or "")
    weather_subject = any(token in normalized for token in ["날씨", "비", "우산", "기온", "온도"])
    weather_verb = any(token in normalized for token in ["알려", "어때", "와", "오니", "오나", "오냐", "오고", "내려", "필요", "몇 도"])
    temporal_or_location = has_date_or_time_signal(normalized) or any(token in normalized for token in ["지금", "현재", "강릉", "서울", "잠실"])

    return weather_subject and (weather_verb or temporal_or_location)


def has_calendar_event_signal(text):
    """Return whether text describes a calendar event domain."""
    normalized = str(text or "")
    subject = any(token in normalized for token in ["일정", "약속", "예약", "만나기", "회의", "미팅"])
    meeting_phrase = "만나" in normalized or "보는" in normalized
    has_date_or_time = has_date_or_time_signal(normalized)
    return has_date_or_time and (subject or meeting_phrase)


def has_date_or_time_signal(text):
    """Return whether text contains a date or clock expression."""
    normalized = str(text or "")

    return bool(re.search(r"\d+\s*(?:월|일|시|:)", normalized)) or any(
        token in normalized for token in ["오늘", "내일", "모레", "이번 주", "다음 주", "오전", "오후"]
    )


def has_relative_reminder_signal(text):
    """Return whether text contains a relative reminder offset."""
    return parse_relative_reminder_minutes(text) is not None


def has_previous_tool(steps, tool_name):
    """Return whether a previous step uses tool_name."""
    return any(step.tool_name == tool_name for step in steps)


def last_tool_index(steps, tool_name):
    """Return last one-based index for a previous tool."""
    for step in reversed(steps):
        if step.tool_name == tool_name:
            return step.index

    return 0


def infer_action(tool_name, text):
    """Infer a concise action label for traces."""
    if tool_name == "calendar":
        if any(token in text for token in ["등록", "추가", "예약", "잡아", "약속"]):
            return "create"
        if any(token in text for token in ["삭제", "취소", "지워"]):
            return "delete"
        return "list"

    if tool_name == "memory":
        if any(token in text for token in ["기억", "저장"]):
            return "remember"
        if any(token in text for token in ["잊어", "삭제"]):
            return "forget"
        return "recall"

    if tool_name == "contacts":
        if any(token in text for token in ["삭제", "지워"]):
            return "delete"
        if any(token in text for token in ["저장", "등록"]):
            return "create"
        if any(token in text for token in ["이메일", "전화번호", "생일"]) and not any(
            token in text for token in ["알려", "찾아", "언제", "뭐", "조회", "보여"]
        ):
            return "update"
        return "get"

    if tool_name == "mail":
        if "답장" in text:
            return "reply"
        if any(token in text for token in ["보내", "전송"]):
            return "send"
        if parse_mail_ordinal(text) > 0 or any(token in text for token in ["읽어", "읽어줘", "본문", "내용"]):
            return "get"
        if any(token in str(text or "").lower() for token in ["github", "openai", "google"]) or any(
            token in text for token in ["깃허브", "오픈", "구글", "안 읽", "오늘"]
        ) or is_mail_keyword_search_command(text):
            return "search"
        return "list"

    if tool_name == "todo":
        if any(token in text for token in ["완료", "끝냄", "끝냈"]):
            return "complete"
        if any(token in text for token in ["삭제", "지워", "취소"]):
            return "delete"
        if any(token in text for token in ["추가", "등록", "넣어"]):
            return "create"
        if any(token in text for token in ["복원", "되살려"]):
            return "restore"
        return "list"

    if tool_name == "reminder":
        return "create"

    if tool_name == "weather":
        return "query"

    if tool_name == "integration_n8n":
        normalized = str(text or "").lower()

        if any(token in normalized for token in ["health", "status", "상태", "연결", "확인", "살아", "괜찮"]):
            return "health"

        if any(token in normalized for token in ["echo", "에코", "보내", "실행", "테스트"]):
            return "execute"

        return "workflow"

    return ""



def should_intent_parser_run_first(text):
    """Return whether NLU should handle ambiguity before metadata routing."""
    normalized = str(text or "")

    if any(
        token in normalized
        for token in [
            "잡고",
            "잡아주고",
            "잡아 주고",
            "등록하고",
            "등록해주고",
            "등록해 주고",
            "추가하고",
            "추가해주고",
            "추가해 주고",
            "넣고",
            "넣어주고",
            "넣어 주고",
        ]
    ) and any(token in normalized for token in ["알려", "알림", "알람"]):
        return True

    if "일정" in normalized and any(token in normalized for token in ["등록", "추가", "잡아", "넣어"]):
        return not any(token in normalized for token in ["시", "오전", "오후", ":"])

    return False


def is_calendar_reminder_rule_candidate(text):
    """Return whether rules can safely split Calendar.create + Reminder.create."""
    normalized = str(text or "")
    has_calendar_create_connector = any(
        token in normalized
        for token in [
            "잡고",
            "잡아주고",
            "잡아 주고",
            "등록하고",
            "등록해주고",
            "등록해 주고",
            "추가하고",
            "추가해주고",
            "추가해 주고",
            "넣고",
            "넣어주고",
            "넣어 주고",
        ]
    )
    has_calendar_create = has_calendar_create_connector or has_calendar_event_signal(normalized)
    return has_calendar_create and has_date_or_time_signal(normalized) and has_relative_reminder_signal(normalized) and contains_reminder_command(normalized)


def is_probable_unresolved_reminder(text):
    """Return whether text sounds like a reminder but lacks a safe time."""
    normalized = str(text or "")
    has_reminder_verb = any(token in normalized for token in ["알려", "알림", "챙겨", "챙기", "말해", "리마인드"])
    has_reminder_object = any(token in normalized for token in ["물", "약", "스트레칭", "운동", "회의", "약속"])
    has_ambiguous_time = any(token in normalized for token in ["조금", "잠깐", "나중", "있다가", "뒤에", "전에", "이따가"])
    has_explicit_minute = bool(re.search(r"\d+\s*(?:분|시간|초)", normalized)) or parse_relative_reminder_minutes(normalized) is not None

    if has_explicit_minute:
        return False

    return has_reminder_verb and (has_reminder_object or has_ambiguous_time)


def should_force_intent_parser():
    """Return whether NLU should run before rule planning for manual tests."""
    return os.environ.get("JARVIS_AI_INTENT_FORCE", "").lower() in ["1", "true", "yes", "on"]


def create_intent_context(registry):
    """Create minimal context for Intent Parser."""
    now = datetime.now()
    available_abilities = []

    if registry is not None:
        try:
            available_abilities = [tool.metadata.name for tool in registry.list()]
        except Exception:
            available_abilities = []

    return IntentContext(
        current_date=now.date().isoformat(),
        current_time=now.time().isoformat(timespec="seconds"),
        timezone="Asia/Seoul",
        available_abilities=tuple(sorted(available_abilities)),
        available_actions=(),
        user_vocabulary={
            "아야": ["아야", "아이", "아야와"],
            "유이": ["유이"],
            "유리": ["유리"],
        },
    )


def execution_step_from_intent(intent, index, context):
    """Translate one structured intent into an ExecutionStep."""
    tool_name = intent_to_tool_name(intent)
    input_data = input_data_from_intent(intent, context)

    if tool_name == "":
        return None

    return ExecutionStep(
        index=index,
        tool_name=tool_name,
        action=intent.action,
        input_data=input_data,
        raw_text=intent.raw_text,
        depends_on=normalize_depends_on(intent.depends_on),
    )


def normalize_depends_on(depends_on):
    """Return one-based dependency indexes from AI output."""
    if depends_on is None:
        return ()

    if isinstance(depends_on, (list, tuple)):
        values = depends_on
    else:
        values = (depends_on,)

    normalized = []

    for value in values:
        try:
            normalized.append(int(value) + 1)
        except (TypeError, ValueError):
            continue

    return tuple(normalized)


def intent_to_tool_name(intent):
    """Return runtime tool name for structured intent."""
    if intent.ability == "integration_n8n":
        return "integration_n8n"

    return intent.ability


def input_data_from_intent(intent, context):
    """Return ability input dictionary for one structured intent."""
    data = {}
    data.update(dict(intent.entities))
    data.update(dict(intent.parameters))
    data.setdefault("raw_text", intent.raw_text)

    if intent.ability == "integration_n8n":
        workflow_key = data.get("workflow_key", "system.health" if intent.action == "health" else "")

        if intent.action == "health":
            workflow_key = "system.health"

        payload = dict(data.get("payload", {}) or {})

        if "message" in data and "message" not in payload:
            payload["message"] = data.get("message", "")

        return {
            "workflow_key": workflow_key,
            "action": workflow_key,
            "payload": payload,
            "raw_text": intent.raw_text,
        }

    if intent.ability == "calendar":
        data["action"] = intent.action
        return data

    if intent.ability == "contacts":
        data["action"] = intent.action
        if "name" in data and "display_name" not in data:
            data["display_name"] = data.get("name", "")
        if "person" in data and "display_name" not in data:
            data["display_name"] = data.get("person", "")
        return data

    if intent.ability == "mail":
        data["action"] = intent.action
        return data

    if intent.ability == "todo":
        data["action"] = intent.action
        if "datetime" in data and "due_at" not in data:
            data["due_at"] = data.get("datetime", "")
        return data

    if intent.ability == "memory":
        data["action"] = intent.action
        return data

    if intent.ability == "reminder":
        data["action"] = "cancel" if intent.action == "cancel" else "list" if intent.action == "list" else "create"

        if "relative_minutes" in data and not data.get("datetime"):
            data["datetime"] = relative_datetime(context, int(data.get("relative_minutes") or 0))

        if "remind_before_minutes" in data and "remind_before" not in data:
            data["remind_before"] = int(data.get("remind_before_minutes") or 0)

        data.setdefault("remind_before", 0)
        return data

    if intent.ability == "weather":
        data.setdefault("text", intent.raw_text)
        return data

    return data


def is_contact_command(text):
    """Return whether text should route to Contact Ability."""
    normalized = str(text or "")

    if is_mail_context_command(normalized):
        return False

    if "연락처" in normalized or "주소록" in normalized:
        return True

    contact_fields = ["이메일", "전화번호", "생일"]
    contact_verbs = ["알려", "언제", "뭐", "조회", "보여", "저장", "등록", "삭제", "지워", "바꿔", "변경", "수정"]
    return any(field in normalized for field in contact_fields) and any(verb in normalized for verb in contact_verbs)


def is_mail_command(text):
    """Return whether text should route to Mail Ability."""
    normalized = corrected_mail_stt_variant(str(text or ""))
    lowered = normalized.lower()
    mail_subject = any(token in normalized for token in ["메일", "이메일"]) or "gmail" in lowered
    mail_verb = any(token in normalized for token in ["알려", "보여", "조회", "검색", "읽어", "읽어줘", "찾아", "보내", "전송", "답장"])
    mail_filter = any(token in normalized for token in ["최근", "오늘", "안 읽", "읽지 않은", "본문", "내용"])
    known_sender = any(token in lowered for token in ["github", "openai", "google"]) or any(
        token in normalized for token in ["깃허브", "구글", "오픈AI", "오픈 AI"]
    )

    if mail_subject and (mail_verb or mail_filter or known_sender):
        return True

    return (
        parse_mail_ordinal(normalized) > 0
        and any(token in normalized for token in ["읽어", "읽어줘", "본문", "내용", "답장"])
    ) or ("답장" in normalized)


def is_mail_context_command(text):
    """Return whether ambiguous email wording is clearly a mailbox request."""
    normalized = str(text or "")
    lowered = normalized.lower()

    if not (any(token in normalized for token in ["메일", "이메일"]) or "gmail" in lowered):
        return False

    mail_context_tokens = ["최근", "오늘", "안 읽", "읽지 않은", "보낸", "받은", "온 메일", "github", "openai", "google", "깃허브", "구글"]

    return any(token in lowered for token in ["github", "openai", "google"]) or any(token in normalized for token in mail_context_tokens)


def corrected_mail_stt_variant(text):
    """Return a conservative mail correction for common STT variants."""
    normalized = " ".join(str(text or "").split()).strip()

    if not any(token in normalized for token in ["알려", "보여", "조회", "검색", "찾아"]):
        return normalized

    if any(token in normalized for token in ["메일", "이메일"]):
        return normalized

    if re.search(r"^최근\s+일\s*(?:알려|보여|조회|검색|찾아)", normalized):
        return normalized.replace("최근 일", "최근 메일", 1)

    match = re.match(r"^(.+?)\s+매일\s*(알려|보여|조회|검색|찾아)(.*)$", normalized)
    if match and match.group(1).strip():
        return f"{match.group(1).strip()} 메일 {match.group(2)}{match.group(3)}".strip()

    return normalized


def is_mail_keyword_search_command(text):
    """Return whether a mail command carries a generic keyword search."""
    normalized = " ".join(corrected_mail_stt_variant(text).split()).strip()

    if not any(token in normalized for token in ["메일", "이메일"]):
        return False

    list_only_tokens = ["최근", "목록", "전체", "받은", "온 메일"]
    body_tokens = ["본문", "내용", "읽어"]
    known_search_tokens = ["안 읽", "읽지 않은", "오늘", "github", "openai", "google", "깃허브", "구글", "오픈AI", "오픈 AI"]

    if any(token in normalized.lower() for token in ["github", "openai", "google"]):
        return False

    if any(token in normalized for token in list_only_tokens + body_tokens + known_search_tokens):
        return False

    cleaned = normalized
    for token in ["메일", "이메일", "알려", "보여", "조회", "검색", "찾아", "줘", "좀", "관련"]:
        cleaned = cleaned.replace(token, " ")

    return bool(cleaned.strip(" .?。"))


def parse_mail_ordinal(text):
    """Return ordinal index for mail follow-up commands."""
    value = str(text or "")
    match = re.search(r"(\d+)\s*번", value)

    if match:
        return int(match.group(1))

    if "이번" in value or "이번에" in value or "첫 번째" in value or "첫번째" in value:
        return 1
    if "두 번째" in value or "두번째" in value:
        return 2
    if "세 번째" in value or "세번째" in value:
        return 3

    return 0


def is_todo_command(text):
    """Return whether text should route to Todo Ability."""
    normalized = str(text or "")
    if any(token in normalized for token in ["할일", "할 일", "투두", "해야 할 일"]):
        return True
    todo_verbs = ["추가", "등록", "저장", "완료", "끝냈", "끝난", "삭제", "지워", "복원"]
    todo_objects = ["우유", "장보기", "사기", "약", "첫 번째", "첫번째", "1번", "2번", "3번"]
    return any(verb in normalized for verb in todo_verbs) and any(obj in normalized for obj in todo_objects)




def relative_datetime(context, minutes):
    """Return ISO datetime relative to current context."""
    base_text = f"{context.current_date}T{context.current_time or '00:00:00'}"

    try:
        base = datetime.fromisoformat(base_text)
    except ValueError:
        base = datetime.now()

    return (base + timedelta(minutes=minutes)).isoformat(timespec="seconds")


