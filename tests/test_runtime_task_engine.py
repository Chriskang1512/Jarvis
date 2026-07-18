import unittest
import io
from contextlib import redirect_stdout
from types import SimpleNamespace

from jarvis.runtime.planner import ExecutionPlan, ExecutionStep
from jarvis.runtime.task import TaskState
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolMetadata, ToolRegistry, ToolResult
from jarvis.native.reminder.reminder import ReminderEntry


class TestRuntimeTaskEngineSprint9(unittest.TestCase):
    """Test Sprint 9 Runtime Task Engine foundation."""

    def test_dispatcher_execute_plan_returns_success_task_history(self):
        """Check a plan is executed as a RuntimeTask and stored in history."""
        registry = ToolRegistry()
        registry.register(StaticTool("echo", response="ok"))
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="echo goal",
            steps=(ExecutionStep(index=1, tool_name="echo", action="run", input_data={}),),
        )

        result = dispatcher.execute_plan(plan)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.task)
        self.assertEqual(result.task.status, TaskState.SUCCESS)
        self.assertEqual(result.task.completed_steps, (1,))
        self.assertEqual(dispatcher.task_history.latest().id, result.task.id)
        self.assertGreaterEqual(result.task.duration_ms, 0)
        self.assertEqual(result.task.step_records[0].duration_ms >= 0, True)

    def test_task_id_flows_through_planner_dispatcher_logs(self):
        """Check Task ID appears on Planner, Dispatcher, and Task summary logs."""
        registry = ToolRegistry()
        registry.register(StaticTool("echo", response="ok"))
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="trace goal",
            steps=(ExecutionStep(index=1, tool_name="echo", action="run", input_data={}),),
        )
        output = io.StringIO()

        with redirect_stdout(output):
            result = dispatcher.execute_plan(plan)

        logs = output.getvalue()
        self.assertIn(f"task={result.task.id}", logs)
        self.assertIn(f"[Task] summary id={result.task.id}", logs)
        self.assertIn("duration=", logs)

    def test_task_runner_retries_retryable_step(self):
        """Check max_retry input drives task step retry."""
        registry = ToolRegistry()
        tool = FlakyTool("flaky", fail_count=1)
        registry.register(tool)
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="retry goal",
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="flaky",
                    action="run",
                    input_data={"max_retry": 1},
                ),
            ),
        )

        result = dispatcher.execute_plan(plan)

        self.assertTrue(result.success)
        self.assertEqual(tool.calls, 2)
        self.assertEqual(result.task.retry_count, 1)
        self.assertEqual(result.task.step_records[0].attempts, 2)

    def test_step_context_feeds_calendar_event_into_reminder(self):
        """Check official step context fills Reminder input from Calendar output."""
        registry = ToolRegistry()
        calendar = CalendarLikeTool()
        reminder = CapturingTool("reminder")
        registry.register(calendar)
        registry.register(reminder)
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="calendar then reminder",
            steps=(
                ExecutionStep(index=1, tool_name="calendar", action="create", input_data={}),
                ExecutionStep(index=2, tool_name="reminder", action="create", input_data={"remind_before": 30}),
            ),
        )

        result = dispatcher.execute_plan(plan)

        self.assertTrue(result.success)
        self.assertEqual(reminder.last_input["title"], "아야 만나기")
        self.assertEqual(reminder.last_input["datetime"], "2026-07-14T15:00:00")
        self.assertEqual(result.task.status, TaskState.SUCCESS)

    def test_partial_success_when_later_step_fails(self):
        """Check Calendar success + Reminder failure becomes partial success."""
        registry = ToolRegistry()
        registry.register(CalendarLikeTool())
        registry.register(FailingTool("reminder", "provider down"))
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="calendar then failed reminder",
            steps=(
                ExecutionStep(index=1, tool_name="calendar", action="create", input_data={}),
                ExecutionStep(index=2, tool_name="reminder", action="create", input_data={}),
            ),
        )

        result = dispatcher.execute_plan(plan)

        self.assertFalse(result.success)
        self.assertEqual(result.task.status, TaskState.PARTIAL_SUCCESS)
        self.assertEqual(result.task.completed_steps, (1,))
        self.assertEqual(result.task.failed_steps, (2,))
        self.assertEqual(result.response, "일정은 등록했습니다. 알림은 등록하지 못했습니다.")

    def test_task_can_be_cancelled_before_next_step(self):
        """Check cancellation stops the next step from running."""
        registry = ToolRegistry()
        second = CapturingTool("reminder")
        dispatcher = RuntimeToolDispatcher(registry)
        registry.register(CancellingTool("calendar", dispatcher))
        registry.register(second)
        plan = ExecutionPlan(
            raw_text="cancel after first step",
            steps=(
                ExecutionStep(index=1, tool_name="calendar", action="create", input_data={}),
                ExecutionStep(index=2, tool_name="reminder", action="create", input_data={}),
            ),
        )

        result = dispatcher.execute_plan(plan)

        self.assertFalse(result.success)
        self.assertEqual(result.task.status, TaskState.CANCELLED)
        self.assertEqual(result.task.completed_steps, (1,))
        self.assertEqual(second.last_input, {})

    def test_reminder_validator_rejects_past_trigger_time(self):
        """Check ReminderValidator prevents invalid reminder success."""
        registry = ToolRegistry()
        registry.register(
            ReminderResultTool(
                ReminderEntry(id="", title="약속", datetime="2000-01-01T09:00:00", remind_before=30)
            )
        )
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="invalid reminder",
            steps=(ExecutionStep(index=1, tool_name="reminder", action="create", input_data={}),),
        )

        result = dispatcher.execute_plan(plan)

        self.assertFalse(result.success)
        self.assertEqual(result.task.status, TaskState.FAILED)
        self.assertEqual(result.step_results[0].failure_reason, "validation_failed")
        self.assertEqual(result.step_results[0].validator, "ReminderValidator")
        self.assertEqual(result.step_results[0].field, "trigger_time")
        self.assertEqual(result.task.step_records[0].failure_reason, "validation_failed")

    def test_reminder_validator_rejects_time_only_title(self):
        """Check ReminderValidator rejects titles made only from time expressions."""
        registry = ToolRegistry()
        registry.register(
            ReminderResultTool(
                ReminderEntry(id="", title="30초", datetime="2099-01-01T09:00:00", remind_before=0)
            )
        )
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="invalid title reminder",
            steps=(ExecutionStep(index=1, tool_name="reminder", action="create", input_data={}),),
        )

        result = dispatcher.execute_plan(plan)

        self.assertFalse(result.success)
        self.assertEqual(result.step_results[0].validator, "ReminderValidator")
        self.assertEqual(result.step_results[0].field, "title")

    def test_reminder_validator_accepts_timezone_aware_future_trigger(self):
        """Check ReminderValidator can compare timezone-aware AI timestamps."""
        registry = ToolRegistry()
        registry.register(
            ReminderResultTool(
                ReminderEntry(id="", title="깨우기", datetime="2099-01-01T09:00:00+09:00", remind_before=0)
            )
        )
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="timezone aware reminder",
            steps=(ExecutionStep(index=1, tool_name="reminder", action="create", input_data={}),),
        )

        result = dispatcher.execute_plan(plan)

        self.assertTrue(result.success)
        self.assertEqual(result.task.status, TaskState.SUCCESS)


class StaticTool:
    """A tiny successful tool."""

    def __init__(self, name, response="ok"):
        self.metadata = ToolMetadata(name=name, description=name)
        self.response = response

    def execute(self, input_data):
        return ToolResult(tool_name=self.metadata.name, success=True, output=self.response)


class CapturingTool(StaticTool):
    """A successful tool that records its input."""

    def __init__(self, name):
        super().__init__(name)
        self.last_input = {}

    def execute(self, input_data):
        self.last_input = dict(input_data)
        return super().execute(input_data)


class FlakyTool(StaticTool):
    """A tool that fails a fixed number of times before succeeding."""

    def __init__(self, name, fail_count):
        super().__init__(name)
        self.fail_count = int(fail_count)
        self.calls = 0

    def execute(self, input_data):
        self.calls += 1

        if self.calls <= self.fail_count:
            return ToolResult(tool_name=self.metadata.name, success=False, error="temporary")

        return super().execute(input_data)


class FailingTool(StaticTool):
    """A permanently failing tool."""

    def __init__(self, name, error):
        super().__init__(name)
        self.error = error

    def execute(self, input_data):
        return ToolResult(tool_name=self.metadata.name, success=False, error=self.error)


class CancellingTool(StaticTool):
    """A tool that requests cancellation after it succeeds."""

    def __init__(self, name, dispatcher):
        super().__init__(name)
        self.dispatcher = dispatcher

    def execute(self, input_data):
        result = super().execute(input_data)
        self.dispatcher.task_runner.cancel_current()
        return result


class CalendarLikeTool(StaticTool):
    """A successful calendar-like tool with event output."""

    def __init__(self):
        super().__init__("calendar")

    def execute(self, input_data):
        event = SimpleNamespace(title="아야 만나기", date="2026-07-14", time="15:00", id="calendar-1")
        data = SimpleNamespace(events=[event], action="create")
        output = SimpleNamespace(data=data, to_natural_language=lambda: "일정을 등록했습니다.")
        return ToolResult(tool_name="calendar", success=True, output=output)


class ReminderResultTool(StaticTool):
    """A reminder-like tool that returns a ReminderResult-shaped output."""

    def __init__(self, reminder):
        super().__init__("reminder")
        self.reminder = reminder

    def execute(self, input_data):
        data = SimpleNamespace(action="create", reminders=[self.reminder])
        output = SimpleNamespace(data=data, to_natural_language=lambda: "알림을 등록했습니다.")
        return ToolResult(tool_name="reminder", success=True, output=output)


if __name__ == "__main__":
    unittest.main()
