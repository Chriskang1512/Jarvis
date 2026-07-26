import unittest
from datetime import date, timedelta
from types import SimpleNamespace

from jarvis.permissions import PermissionLevel
from jarvis.abilities import AbilityRegistry
from jarvis.abilities.operations import CapabilityOperationMetadata
from jarvis.runtime.planner import (
    ExecutionPlan,
    ExecutionStep,
    HealthReason,
    HealthRecoveryPolicy,
    RuntimePlanner,
)
from jarvis.runtime.task import InMemoryTaskCheckpointStore, TaskState, TaskStateMachine
from jarvis.runtime.tool_dispatcher import (
    InMemoryPendingExecutionStore,
    RuntimeToolDispatcher,
)
from jarvis.tools import ToolMetadata, ToolRegistry, ToolResult


class TestAgentCoreMultiStepVerticalSlice(unittest.TestCase):
    def test_planner_builds_calendar_reminder_mail_dependency_chain(self):
        registry = create_registry()
        plan = RuntimePlanner().plan(
            "내일 오후 3시에 アヤ와 미팅을 만들고 하루 전에 알려주는 "
            "리마인더를 추가하고 일정 내용을 메일 초안으로 작성해.",
            registry,
        )

        self.assertEqual(
            [(step.tool_name, step.action) for step in plan.steps],
            [("calendar", "create"), ("reminder", "create"), ("mail", "send")],
        )
        self.assertEqual(plan.steps[1].depends_on, (1,))
        self.assertEqual(plan.steps[2].depends_on, (1, 2))
        self.assertEqual(plan.steps[1].input_data["remind_before"], 1440)

    def test_happy_path_uses_one_task_and_records_replayable_journal(self):
        registry = create_registry()
        dispatcher = RuntimeToolDispatcher(registry)
        plan = vertical_slice_plan()

        waiting = dispatcher.execute_plan(plan)

        self.assertEqual(waiting.task.status, TaskState.WAIT_CONFIRM)
        self.assertEqual(waiting.task.completed_steps, (1, 2))
        self.assertEqual(registry.get("mail").calls, 0)
        self.assertEqual(
            [item.artifact_type for item in waiting.task.conversation_context.pending_artifacts],
            ["mail_draft"],
        )

        completed = dispatcher.confirm_task(waiting.task.id)

        self.assertTrue(completed.success)
        self.assertEqual(completed.task.id, waiting.task.id)
        self.assertEqual(completed.task.status, TaskState.SUCCESS)
        self.assertEqual(completed.task.completed_steps, (1, 2, 3))
        self.assertEqual(registry.get("calendar").calls, 1)
        self.assertEqual(registry.get("reminder").calls, 1)
        self.assertEqual(registry.get("mail").calls, 1)
        self.assertEqual(completed.task.conversation_context.pending_artifacts, ())

        replay = dispatcher.execution_journal.replay(completed.task.id)
        self.assertTrue(replay.valid)
        execution_steps = [
            entry.metadata.get("step_id")
            for entry in replay.entries
            if entry.event == "STEP_COMPLETED"
        ]
        self.assertEqual(execution_steps, ["1", "2", "3"])
        phases = {entry.phase.value for entry in replay.entries}
        self.assertTrue(
            {
                "GOAL",
                "PLAN",
                "DISCOVERY",
                "PERMISSION",
                "EXECUTION",
                "VERIFICATION",
                "RESULT",
            }.issubset(phases)
        )
        explanation = dispatcher.execution_journal.explain(completed.task.id)
        self.assertIn("DISCOVERY:CAPABILITY_SELECTED:DEPENDENCY_ROOT", explanation.reasons)

    def test_cancel_stops_mail_but_preserves_completed_calendar_and_reminder(self):
        registry = create_registry()
        dispatcher = RuntimeToolDispatcher(registry)
        waiting = dispatcher.execute_plan(vertical_slice_plan())

        cancelled = dispatcher.cancel_task(waiting.task.id)

        self.assertTrue(cancelled.success)
        self.assertEqual(cancelled.task.id, waiting.task.id)
        self.assertEqual(cancelled.task.status, TaskState.CANCELLED)
        self.assertEqual(cancelled.task.completed_steps, (1, 2))
        self.assertEqual(registry.get("calendar").calls, 1)
        self.assertEqual(registry.get("reminder").calls, 1)
        self.assertEqual(registry.get("mail").calls, 0)
        self.assertEqual(cancelled.task.conversation_context.pending_artifacts, ())
        self.assertIn(
            "SUCCESS_CANCELLED_BRANCH",
            [entry.status for entry in dispatcher.execution_journal.query(task_id=cancelled.task.id)],
        )

    def test_paused_task_resumes_after_runtime_is_recreated(self):
        pending_store = InMemoryPendingExecutionStore()
        checkpoint_store = InMemoryTaskCheckpointStore()
        state_machine = TaskStateMachine(checkpoint_store=checkpoint_store)
        registry = ToolRegistry()
        tool = RecoveringTool()
        registry.register(tool)
        decision = HealthRecoveryPolicy().evaluate(HealthReason.AUTH_FAILURE)
        plan = ExecutionPlan(
            raw_text="resume after authentication",
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="mail",
                    action="send",
                    input_data={"_recovery_decision": decision},
                ),
            ),
        )
        first_runtime = RuntimeToolDispatcher(
            registry,
            state_machine=state_machine,
            pending_execution_store=pending_store,
        )

        paused = first_runtime.execute_plan(plan)
        self.assertEqual(paused.task.status, TaskState.PAUSED)
        tool.available = True

        restarted_runtime = RuntimeToolDispatcher(
            registry,
            state_machine=state_machine,
            pending_execution_store=pending_store,
            execution_journal=first_runtime.execution_journal,
        )
        resumed = restarted_runtime.resume_task(paused.task.id, decision)

        self.assertEqual(resumed.task.id, paused.task.id)
        self.assertEqual(resumed.task.status, TaskState.SUCCESS)
        self.assertEqual(tool.calls, 2)
        states = [item.to_state for item in resumed.task.transition_history]
        self.assertIn(TaskState.PAUSED, states)
        self.assertIn(TaskState.RESUMING, states)

    def test_retry_follows_recovery_decision_and_succeeds(self):
        registry = ToolRegistry()
        tool = RetryTool()
        registry.register(tool)
        decision = HealthRecoveryPolicy().evaluate(HealthReason.TIMEOUT)
        plan = ExecutionPlan(
            raw_text="retry mail",
            steps=(
                ExecutionStep(
                    index=1,
                    tool_name="mail",
                    action="draft",
                    input_data={
                        "_recovery_decision": decision,
                        "retry_delay_seconds": 0,
                    },
                ),
            ),
        )
        dispatcher = RuntimeToolDispatcher(registry)

        result = dispatcher.execute_plan(plan)

        self.assertEqual(result.task.status, TaskState.SUCCESS)
        self.assertEqual(tool.calls, 2)
        self.assertEqual(result.task.retry_count, 1)
        events = [entry.event for entry in dispatcher.execution_journal.query(task_id=result.task.id)]
        self.assertIn("RECOVERY_DECIDED", events)

    def test_verification_failure_rolls_back_side_effect(self):
        registry = ToolRegistry()
        calendar = VerificationFailingCalendarTool()
        registry.register(calendar)
        dispatcher = RuntimeToolDispatcher(registry)
        plan = ExecutionPlan(
            raw_text="create invalid calendar event",
            steps=(ExecutionStep(index=1, tool_name="calendar", action="create"),),
        )

        result = dispatcher.execute_plan(plan)

        self.assertEqual(result.task.status, TaskState.FAILED)
        self.assertEqual(calendar.calls, 1)
        self.assertEqual(calendar.rollbacks, 1)
        entries = dispatcher.execution_journal.query(task_id=result.task.id)
        self.assertIn("ROLLBACK_COMPLETED", [entry.event for entry in entries])


def vertical_slice_plan():
    return ExecutionPlan(
        raw_text="calendar reminder and mail",
        steps=(
            ExecutionStep(
                index=1,
                tool_name="calendar",
                action="create",
                input_data={"title": "Aya meeting", "date": "2099-01-02", "time": "15:00"},
            ),
            ExecutionStep(
                index=2,
                tool_name="reminder",
                action="create",
                input_data={"remind_before": 1440},
                depends_on=(1,),
            ),
            ExecutionStep(
                index=3,
                tool_name="mail",
                action="send",
                input_data={
                    "recipient": "aya@example.com",
                    "_workspace_calendar_mail": True,
                },
                depends_on=(1, 2),
            ),
        ),
    )


def create_registry():
    registry = ToolRegistry()
    registry.register(CalendarTool())
    registry.register(ReminderTool())
    registry.register(MailTool())
    ability_registry = AbilityRegistry()
    for capability, operation in (
        ("calendar", "create"),
        ("reminder", "create"),
        ("mail", "send"),
    ):
        ability_registry.register_operation(
            CapabilityOperationMetadata(
                capability=capability,
                operation=operation,
                permission="confirm_required" if capability == "mail" else "safe",
                side_effect="external_write",
            )
        )
    registry.ability_registry = ability_registry
    return registry


class CalendarTool:
    def __init__(self):
        self.metadata = ToolMetadata(name="calendar", description="calendar")
        self.calls = 0

    def execute(self, input_data):
        self.calls += 1
        event = SimpleNamespace(
            title=input_data.get("title", "Aya meeting"),
            date=input_data.get("date", "2099-01-02"),
            time=input_data.get("time", "15:00"),
            id="event-1",
        )
        data = SimpleNamespace(action="create", events=[event])
        return ToolResult("calendar", True, SimpleNamespace(data=data))


class ReminderTool:
    def __init__(self):
        self.metadata = ToolMetadata(name="reminder", description="reminder")
        self.calls = 0

    def execute(self, input_data):
        self.calls += 1
        event_time = str(input_data.get("datetime", "2099-01-02T15:00:00"))
        reminder = SimpleNamespace(
            title=input_data.get("title", "Aya meeting"),
            datetime=event_time,
            trigger_time=(date.today() + timedelta(days=1)).isoformat() + "T15:00:00",
        )
        data = SimpleNamespace(action="create", reminders=[reminder])
        return ToolResult("reminder", True, SimpleNamespace(data=data))


class MailTool:
    def __init__(self):
        self.metadata = ToolMetadata(
            name="mail",
            description="mail",
            permission_level=PermissionLevel.CONFIRM,
        )
        self.calls = 0

    def execute(self, input_data):
        self.calls += 1
        return ToolResult("mail", True, "sent")


class RecoveringTool:
    def __init__(self):
        self.metadata = ToolMetadata(name="mail", description="mail")
        self.available = False
        self.calls = 0

    def execute(self, input_data):
        self.calls += 1
        if not self.available:
            return ToolResult("mail", False, error="authentication failed")
        return ToolResult("mail", True, "sent")


class RetryTool:
    def __init__(self):
        self.metadata = ToolMetadata(name="mail", description="mail")
        self.calls = 0

    def execute(self, input_data):
        self.calls += 1
        if self.calls == 1:
            return ToolResult("mail", False, error="timeout")
        return ToolResult("mail", True, "drafted")


class VerificationFailingCalendarTool(CalendarTool):
    def __init__(self):
        super().__init__()
        self.rollbacks = 0

    def execute(self, input_data):
        result = super().execute(input_data)
        result.verification_success = False
        result.verification_validator = "CalendarResultValidator"
        result.verification_error = "created event metadata mismatch"
        return result

    def rollback(self, input_data, tool_result):
        self.rollbacks += 1


if __name__ == "__main__":
    unittest.main()
