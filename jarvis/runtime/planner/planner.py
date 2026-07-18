import os
import re
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

        if self.intent_parser is not None and should_force_intent_parser():
            intent_plan = self.create_intent_plan(raw_text, registry)

            if intent_plan is not None and (intent_plan.step_count > 0 or intent_plan.requires_clarification or intent_plan.unsupported_reason or intent_plan.intent_error):
                trace_plan(intent_plan)
                return intent_plan

        if (
            self.intent_parser is not None
            and should_intent_parser_run_first(raw_text)
            and not is_calendar_reminder_rule_candidate(raw_text)
        ):
            intent_plan = self.create_intent_plan(raw_text, registry)

            if intent_plan is not None:
                trace_plan(intent_plan)
                return intent_plan

        clauses = split_plan_clauses(raw_text)
        steps = []

        for clause in clauses:
            step = self.create_step(clause, registry, steps)

            if step is not None:
                steps.append(step)

        plan = ExecutionPlan(raw_text=raw_text, steps=tuple(steps))

        if plan.step_count == 0 and self.intent_parser is not None:
            intent_plan = self.create_intent_plan(raw_text, registry)

            if intent_plan is not None:
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
    if "날씨" in text:
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

    if is_todo_command(text):
        tool = registry.get("todo")

        if tool is not None:
            return {"tool": tool, "confidence": 0.9, "input_data": {"text": text}}

    if contains_reminder_command(text):
        tool = registry.get("reminder")

        if tool is not None:
            return {"tool": tool, "confidence": 0.8, "input_data": {"text": text}}

    return None


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


def split_attached_and(text):
    """Split Korean attached connector forms such as '등록하고'."""
    value = str(text or "").strip()

    if value == "":
        return []

    match = re.search(r"(.+?)(등록하고|추가하고|잡고|알려주고|알려 줘고)\s+(.+)", value)

    if not match:
        return [value]

    first = (match.group(1) + match.group(2)).strip()
    connector = match.group(2)
    if connector in {"등록하고", "추가하고"}:
        first = re.sub(r"하고$", "", first)
    elif connector == "잡고":
        first = re.sub(r"잡고$", "잡아 줘", first)
    elif connector in {"알려주고", "알려 줘고"}:
        first = re.sub(r"알려\s*주고$", "알려줘", first)

    second = match.group(3).strip()
    return [first.strip(), second]






def normalize_clause(clause):
    """Normalize one clause after connector splitting."""
    text = " ".join(str(clause or "").strip().split())
    return text.strip(" .?!")


def parse_reminder_follow_up(text):
    """Return Reminder input data for a calendar-relative reminder clause."""
    minute_match = re.search(r"(\d+)\s*분\s*전", text)
    hour_match = re.search(r"(\d+)\s*시간\s*전", text)

    if not contains_reminder_command(text):
        return None

    if hour_match:
        remind_before = int(hour_match.group(1)) * 60
    elif minute_match:
        remind_before = int(minute_match.group(1))
    else:
        return None

    return {
        "action": "create",
        "title": "",
        "datetime": "",
        "remind_before": remind_before,
        "raw_text": text,
    }


def contains_reminder_command(text):
    """Return whether text asks to notify the user."""
    return any(token in text for token in ["알려줘", "알려 줘", "알림", "알람", "챙기라고", "하라고"])


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

    if explicit_reminder and not any(token in normalized for token in ["일정", "약속", "예약"]):
        return False

    return calendar_subject and create_verb


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
        if any(token in text for token in ["이메일", "전화번호", "생일"]) and not any(token in text for token in ["알려", "언제", "뭐", "조회", "보여"]):
            return "update"
        return "get"

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

    if any(token in normalized for token in ["잡고", "등록하고", "추가하고"]) and any(token in normalized for token in ["알려", "알림"]):
        return True

    if "일정" in normalized and any(token in normalized for token in ["등록", "추가", "잡아", "넣어"]):
        return not any(token in normalized for token in ["시", "오전", "오후", ":"])

    return False


def is_calendar_reminder_rule_candidate(text):
    """Return whether rules can safely split Calendar.create + Reminder.create."""
    normalized = str(text or "")
    has_calendar_create = any(token in normalized for token in ["잡고", "잡아주고", "잡아 주고", "등록하고", "추가하고"])
    has_date_or_time = any(token in normalized for token in ["오늘", "내일", "모레", "오전", "오후", "시", ":"])
    has_relative_reminder = bool(re.search(r"\d+\s*(?:분|시간)\s*전", normalized))
    return has_calendar_create and has_date_or_time and has_relative_reminder and contains_reminder_command(normalized)


def is_probable_unresolved_reminder(text):
    """Return whether text sounds like a reminder but lacks a safe time."""
    normalized = str(text or "")
    has_reminder_verb = any(token in normalized for token in ["알려", "알림", "챙겨", "챙기", "말해", "리마인드"])
    has_reminder_object = any(token in normalized for token in ["물", "약", "스트레칭", "운동", "회의", "약속"])
    has_ambiguous_time = any(token in normalized for token in ["조금", "잠깐", "나중", "있다가", "뒤에", "전에", "이따가"])
    has_explicit_minute = bool(re.search(r"\d+\s*(?:분|시간|초)", normalized))

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

    if "연락처" in normalized or "주소록" in normalized:
        return True

    contact_fields = ["이메일", "전화번호", "생일"]
    contact_verbs = ["알려", "언제", "뭐", "조회", "보여", "저장", "등록", "삭제", "지워"]
    return any(field in normalized for field in contact_fields) and any(verb in normalized for verb in contact_verbs)


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


