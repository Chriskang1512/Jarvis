import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from time import perf_counter, sleep

from jarvis.debug_trace import trace_event
from jarvis.runtime.planner import PlanResult, PlanStepResult
from jarvis.runtime.task.history import TaskHistory
from jarvis.runtime.task.models import RuntimeTask, TaskState, TaskStepRecord, now_iso


@dataclass(frozen=True)
class TaskRunnerResult:
    """Result of running one RuntimeTask."""

    task: RuntimeTask
    plan_result: PlanResult
    context: dict = field(default_factory=dict)


class TaskRunner:
    """Execute an ExecutionPlan as a stateful RuntimeTask."""

    def __init__(
        self,
        execute_step,
        resolve_step_input,
        format_response,
        update_context,
        merge_responses,
        history=None,
    ):
        """Create a task runner from dispatcher callbacks."""
        self.execute_step = execute_step
        self.resolve_step_input = resolve_step_input
        self.format_response = format_response
        self.update_context = update_context
        self.merge_responses = merge_responses
        self.history = history or TaskHistory()
        self._cancelled_task_ids = set()
        self._active_task_id = ""

    def cancel(self, task_id):
        """Mark a task ID as cancelled before the next step starts."""
        self._cancelled_task_ids.add(str(task_id or ""))

    def cancel_current(self):
        """Cancel the currently running task before the next step starts."""
        if self._active_task_id:
            self.cancel(self._active_task_id)

    def run(self, plan, confirmed=False, start_index=0, initial_context=None, pre_step_results=None):
        """Execute a plan and return a TaskRunnerResult."""
        started = perf_counter()
        task = RuntimeTask(id="", goal=getattr(plan, "raw_text", "") or getattr(plan, "id", ""))
        task = task.transition(TaskState.RUNNING)
        self._active_task_id = task.id
        trace_event("task.started", task_id=task.id, goal=task.goal, step_count=getattr(plan, "step_count", 0))

        try:
            context = dict(initial_context or {})
            step_results = list(pre_step_results or [])
            completed_steps = []
            failed_steps = []
            step_records = []
            total_retry_count = 0

            for step in tuple(getattr(plan, "steps", []))[int(start_index or 0) :]:
                if task.id in self._cancelled_task_ids:
                    task = task.transition(
                        TaskState.CANCELLED,
                        current_step=step.index,
                        completed_steps=tuple(completed_steps),
                        failed_steps=tuple(failed_steps),
                        retry_count=total_retry_count,
                        step_records=tuple(step_records),
                        duration_ms=elapsed_ms(started),
                    )
                    return self.finish(task, plan, step_results, context, "cancelled")

                input_data = self.resolve_step_input(step, context)

                if should_suppress_calendar_auto_reminder(plan, step):
                    input_data["_suppress_auto_reminder"] = True

                if confirmed:
                    input_data["_confirmed"] = True

                task = task.transition(TaskState.RUNNING, current_step=step.index)
                trace_event(
                    "task.step.started",
                    task_id=task.id,
                    step_index=step.index,
                    step_count=getattr(plan, "step_count", 0),
                    tool=step.tool_name,
                    action=step.action,
                )
                step_result, record, retry_count = self.run_step(
                    step,
                    input_data,
                    getattr(plan, "step_count", 0),
                    task.id,
                )
                total_retry_count += retry_count
                step_results.append(step_result)

                if is_confirm_required_step_result(step_result):
                    wait_record = replace(record, status=TaskState.WAIT_CONFIRM)
                    step_records.append(wait_record)
                    task = task.transition(
                        TaskState.WAIT_CONFIRM,
                        current_step=step.index,
                        completed_steps=tuple(completed_steps),
                        failed_steps=tuple(failed_steps),
                        retry_count=total_retry_count,
                        step_records=tuple(step_records),
                        duration_ms=elapsed_ms(started),
                    )
                    return self.finish(task, plan, step_results, context, "confirm_required")

                step_records.append(record)

                if step_result.success:
                    completed_steps.append(step.index)
                    self.update_context(context, step, getattr(step_result, "tool_result", None))
                    continue

                failed_steps.append(step.index)
                final_state = TaskState.PARTIAL_SUCCESS if len(completed_steps) > 0 else TaskState.FAILED
                task = task.transition(
                    final_state,
                    completed_steps=tuple(completed_steps),
                    failed_steps=tuple(failed_steps),
                    retry_count=total_retry_count,
                    step_records=tuple(step_records),
                    duration_ms=elapsed_ms(started),
                )
                return self.finish(task, plan, step_results, context, step_result.error)

            task = task.transition(
                TaskState.SUCCESS if len(step_results) > 0 else TaskState.FAILED,
                completed_steps=tuple(completed_steps),
                failed_steps=tuple(failed_steps),
                retry_count=total_retry_count,
                step_records=tuple(step_records),
                duration_ms=elapsed_ms(started),
            )
            return self.finish(task, plan, step_results, context, "")
        finally:
            self._active_task_id = ""

    def run_step(self, step, input_data, step_count, task_id):
        """Execute one step with retry and validation."""
        started_at = now_iso()
        step_started = perf_counter()
        max_retry = read_retry_count(step, input_data)
        retry_delay = read_retry_delay(step, input_data)
        attempts = 0
        retry_count = 0
        last_result = None

        while True:
            attempts += 1
            tool_result = self.execute_step(step, dict(input_data), step_count, task_id=task_id)
            response = self.format_response(tool_result)
            validation = validate_tool_result(step, tool_result)
            if not validation["success"]:
                response = validation["error"]
            step_result = PlanStepResult(
                step_index=step.index,
                tool_name=step.tool_name,
                success=getattr(tool_result, "success", False) and validation["success"],
                response=response,
                tool_result=tool_result,
                error=getattr(tool_result, "error", "") or validation["error"],
                failure_reason=validation["reason"],
                validator=validation["validator"],
                field=validation["field"],
            )
            last_result = step_result

            if validate_step_result(step_result):
                record = TaskStepRecord(
                    step_index=step.index,
                    tool_name=step.tool_name,
                    action=step.action,
                    status=TaskState.SUCCESS,
                    attempts=attempts,
                    response=response,
                    started_at=started_at,
                    completed_at=now_iso(),
                    duration_ms=elapsed_ms(step_started),
                )
                trace_event(
                    "task.step.completed",
                    task_id=task_id,
                    step_index=step.index,
                    tool=step.tool_name,
                    attempts=attempts,
                    duration_ms=record.duration_ms,
                )
                return step_result, record, retry_count

            if retry_count >= max_retry:
                record = TaskStepRecord(
                    step_index=step.index,
                    tool_name=step.tool_name,
                    action=step.action,
                    status=TaskState.FAILED,
                    attempts=attempts,
                    response=response,
                    error=step_result.error,
                    failure_reason=step_result.failure_reason,
                    validator=step_result.validator,
                    field=step_result.field,
                    started_at=started_at,
                    completed_at=now_iso(),
                    duration_ms=elapsed_ms(step_started),
                )
                trace_event(
                    "task.step.failed",
                    task_id=task_id,
                    step_index=step.index,
                    tool=step.tool_name,
                    attempts=attempts,
                    error=step_result.error,
                    reason=step_result.failure_reason,
                    validator=step_result.validator,
                    field=step_result.field,
                    duration_ms=record.duration_ms,
                )
                return last_result, record, retry_count

            retry_count += 1
            trace_event(
                "task.step.retry",
                task_id=task_id,
                step_index=step.index,
                tool=step.tool_name,
                retry_count=retry_count,
                max_retry=max_retry,
            )

            if retry_delay > 0:
                sleep(retry_delay)

    def finish(self, task, plan, step_results, context, error):
        """Build PlanResult, save history, and return TaskRunnerResult."""
        success = task.status in (TaskState.SUCCESS, TaskState.WAIT_CONFIRM)
        response = self.merge_responses(step_results, plan)

        if task.status == TaskState.PARTIAL_SUCCESS:
            response = partial_success_response(step_results)

        plan_result = PlanResult(
            success=success,
            plan=plan,
            step_results=step_results,
            response=response,
            error=error,
            task=task,
        )
        self.history.add(task)
        trace_event(
            "task.completed",
            task_id=task.id,
            status=task.status.value,
            duration_ms=task.duration_ms,
            step_count=len(step_results),
            retry_count=task.retry_count,
        )
        trace_event(
            "task.summary",
            task_id=task.id,
            status=task.status.value,
            duration_ms=task.duration_ms,
            step_count=len(step_results),
            retry_count=task.retry_count,
        )
        return TaskRunnerResult(task=task, plan_result=plan_result, context=context)


def validate_step_result(step_result):
    """Return whether one step result is valid enough to continue."""
    return bool(getattr(step_result, "success", False))


def validate_tool_result(step, tool_result):
    """Return structured validation for one executed tool result."""
    if getattr(step, "tool_name", "") == "reminder":
        return validate_reminder_tool_result(tool_result)

    return valid_validation()


def validate_reminder_tool_result(tool_result):
    """Validate ReminderResult before a task step is marked successful."""
    if not getattr(tool_result, "success", False):
        return valid_validation()

    output = getattr(tool_result, "output", None)
    data = getattr(output, "data", output)

    if getattr(data, "action", "") != "create":
        return valid_validation()

    reminders = list(getattr(data, "reminders", []) or [])

    if len(reminders) == 0:
        return invalid_validation("validation_failed", "ReminderValidator", "reminders", "알림 생성 결과가 비어 있습니다.")

    for reminder in reminders:
        issue = validate_one_reminder(reminder)

        if not issue["success"]:
            return issue

    return valid_validation()


def validate_one_reminder(reminder):
    """Validate one scheduled reminder entry."""
    title = str(getattr(reminder, "title", "") or "").strip()
    trigger_time = str(getattr(reminder, "trigger_time", "") or "").strip()
    event_time = str(getattr(reminder, "datetime", "") or "").strip()

    if title == "":
        return invalid_validation("validation_failed", "ReminderValidator", "title", "알림 제목이 비어 있습니다.")

    if is_time_only_title(title):
        return invalid_validation("validation_failed", "ReminderValidator", "title", "알림 제목이 시간 표현만으로 되어 있습니다.")

    try:
        trigger = datetime.fromisoformat(trigger_time)
    except ValueError:
        return invalid_validation("validation_failed", "ReminderValidator", "trigger_time", "알림 시간이 올바르지 않습니다.")

    try:
        datetime.fromisoformat(event_time)
    except ValueError:
        return invalid_validation("validation_failed", "ReminderValidator", "datetime", "기준 시간이 올바르지 않습니다.")

    if trigger <= comparable_now(trigger):
        return invalid_validation("validation_failed", "ReminderValidator", "trigger_time", "알림 시간이 이미 지났습니다.")

    return valid_validation()


def is_time_only_title(title):
    """Return whether a title is only a duration/time expression."""
    normalized = re.sub(r"\s+", "", str(title or "")).lower()
    return bool(
        re.fullmatch(
            r"\d+(\uCD08|\uBD84|\uC2DC\uAC04|\uC2DC|\uC77C|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hour|hours)",
            normalized,
        )
    )


def comparable_now(value):
    """Return now with timezone awareness matching value."""
    if getattr(value, "tzinfo", None) is not None:
        return datetime.now(value.tzinfo)

    return datetime.now()


def valid_validation():
    """Return a successful validation payload."""
    return {"success": True, "reason": "", "validator": "", "field": "", "error": ""}


def invalid_validation(reason, validator, field, error):
    """Return a failed validation payload."""
    return {"success": False, "reason": reason, "validator": validator, "field": field, "error": error}


def is_confirm_required_step_result(step_result):
    """Return whether a step is waiting for user confirmation."""
    tool_result = getattr(step_result, "tool_result", None)
    output = getattr(tool_result, "output", None)
    metadata = getattr(output, "metadata", {}) or {}
    return metadata.get("permission") == "confirm_required"


def should_suppress_calendar_auto_reminder(plan, step):
    """Return whether an explicit later Reminder step owns reminder creation."""
    if getattr(step, "tool_name", "") != "calendar":
        return False

    for later_step in getattr(plan, "steps", []) or []:
        if getattr(later_step, "tool_name", "") != "reminder":
            continue

        if int(getattr(step, "index", 0) or 0) in tuple(getattr(later_step, "depends_on", ()) or ()):
            return True

    return False


def read_retry_count(step, input_data):
    """Return max retry count from step input."""
    for key in ["max_retry", "max_retries"]:
        try:
            return max(0, int(input_data.get(key, 0) or 0))
        except (TypeError, ValueError):
            return 0

    return 0


def read_retry_delay(step, input_data):
    """Return retry delay seconds from step input."""
    try:
        return max(0.0, float(input_data.get("retry_delay_seconds", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def partial_success_response(step_results):
    """Return a concise partial success response."""
    successes = [result for result in step_results if result.success]
    failures = [result for result in step_results if not result.success]

    success_text = "일부 작업은 완료했습니다."
    failure_text = "일부 작업은 완료하지 못했습니다."

    if any(result.tool_name == "calendar" for result in successes):
        success_text = "일정은 등록했습니다."

    if any(result.tool_name == "reminder" for result in failures):
        failure_text = "알림은 등록하지 못했습니다."

    return f"{success_text} {failure_text}"


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)
