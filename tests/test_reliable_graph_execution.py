import random
import unittest
from dataclasses import dataclass, replace
from types import SimpleNamespace

from jarvis.capability_planning import (
    PlannerStatus,
    SuccessCriterionMapping,
)
from jarvis.goals import GoalSpecification, SuccessCriterion
from jarvis.graph_execution import (
    CapabilityExecutionAdapter,
    ErrorCategory,
    ExecutionWaitingReason,
    ExecutionOutcome,
    GraphExecutionSession,
    GraphExecutionState,
    GraphExecutor,
    NodeResultVerifier,
    RecoveryController,
    ReplanController,
    ReplanTrigger,
    RetryController,
    VerificationStatus,
    TypedOutput,
)
from jarvis.native_task_graph import (
    BackoffStrategy,
    GraphOutput,
    GraphExecutionPolicy,
    NativeTaskGraph,
    OutputDefinition,
    PermissionRequirement,
    RetryPolicy,
    TaskNode,
    NodeType,
    VerificationLevel,
    VerificationPolicy,
)
from tests.test_graph_executor_runtime import literal, metadata, validated_snapshot


def graph_for(node):
    return NativeTaskGraph(
        f"graph-{node.node_id}",
        "goal-reliable",
        "conversation",
        nodes=(node,),
        outputs=tuple(
            GraphOutput(
                key, node.node_id, key, definition.value_type, is_primary=True
            )
            for key, definition in node.outputs.items()
        ),
        metadata=metadata(),
    )


class TestReliableGraphExecution(unittest.TestCase):
    def test_schema_verification_passes_and_required_output_fails(self):
        node = TaskNode(
            "schema",
            NodeType.CAPABILITY,
            "system.schema",
            "schema",
            outputs={"result": OutputDefinition("result", "string")},
            verification_policy=VerificationPolicy(
                VerificationLevel.SCHEMA
            ),
        )
        verifier = NodeResultVerifier()
        passed = verifier.verify(node, {}, {"result": "ok"})
        failed = verifier.verify(node, {}, {})
        mismatch = verifier.verify(node, {}, {"result": 3})

        self.assertEqual(VerificationStatus.PASSED, passed.status)
        self.assertEqual(VerificationStatus.FAILED, failed.status)
        self.assertIn("required_output_missing:result", failed.problems)
        self.assertIn("output_type_mismatch:result", mismatch.problems)

    def test_semantic_and_external_read_back(self):
        node = TaskNode(
            "update",
            NodeType.CAPABILITY,
            "calendar.update_event",
            "update_event",
            inputs={"time": literal("16:00")},
            outputs={"event": OutputDefinition("event", "CalendarEvent")},
            permission_requirement=PermissionRequirement.CONFIRM_REQUIRED,
            verification_policy=VerificationPolicy(
                VerificationLevel.EXTERNAL_READ_BACK,
                read_back_capability_id="calendar.get_event",
            ),
        )
        verifier = NodeResultVerifier()
        adapter = CapabilityExecutionAdapter(
            handlers={
                "calendar.get_event": lambda _: {"start_time": "16:00"}
            }
        )
        passed = verifier.verify(
            node,
            {"time": "16:00"},
            {"event": {"start_time": "16:00"}},
            adapter=adapter,
        )
        adapter.handlers["calendar.get_event"] = lambda _: {
            "start_time": "15:00"
        }
        failed = verifier.verify(
            node,
            {"time": "16:00"},
            {"event": {"start_time": "16:00"}},
            adapter=adapter,
        )

        self.assertEqual(VerificationStatus.PASSED, passed.status)
        self.assertEqual(VerificationStatus.FAILED, failed.status)

    def test_retry_controller_backoff_and_jitter(self):
        controller = RetryController(random_source=random.Random(3))
        fixed = RetryPolicy(
            max_attempts=3,
            delay_seconds=2,
            max_delay_seconds=10,
            backoff_strategy=BackoffStrategy.FIXED,
        )
        exponential = replace(
            fixed, backoff_strategy=BackoffStrategy.EXPONENTIAL
        )
        jitter = replace(exponential, jitter=True)

        self.assertEqual(
            2,
            controller.decide(
                policy=fixed,
                attempt_number=1,
                error_category=ErrorCategory.TIMEOUT,
            ).delay_seconds,
        )
        self.assertEqual(
            4,
            controller.decide(
                policy=exponential,
                attempt_number=2,
                error_category=ErrorCategory.TIMEOUT,
            ).delay_seconds,
        )
        jitter_delay = controller.decide(
            policy=jitter,
            attempt_number=2,
            error_category=ErrorCategory.TIMEOUT,
        ).delay_seconds
        self.assertGreaterEqual(jitter_delay, 2)
        self.assertLessEqual(jitter_delay, 4)
        self.assertTrue(
            controller.decide(
                policy=fixed,
                attempt_number=3,
                error_category=ErrorCategory.TIMEOUT,
            ).exhausted
        )
        self.assertFalse(
            controller.decide(
                policy=fixed,
                attempt_number=1,
                error_category=ErrorCategory.INVALID_INPUT,
            ).should_retry
        )
        fallback_policy = replace(
            fixed, provider_fallback_allowed=True
        )
        self.assertTrue(
            controller.decide(
                policy=fallback_policy,
                attempt_number=1,
                error_category=ErrorCategory.TIMEOUT,
                external_mutation=False,
            ).use_fallback_provider
        )
        self.assertFalse(
            controller.decide(
                policy=fallback_policy,
                attempt_number=1,
                error_category=ErrorCategory.TIMEOUT,
                external_mutation=True,
            ).use_fallback_provider
        )

    def test_timeout_retries_with_same_idempotency_key(self):
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "Any")},
            retry_policy=RetryPolicy(
                max_attempts=3,
                delay_seconds=0,
                backoff_strategy=BackoffStrategy.EXPONENTIAL,
                retryable_categories=("Timeout",),
            ),
            verification_policy=VerificationPolicy(
                VerificationLevel.SCHEMA
            ),
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        calls = []

        def handler(inputs):
            calls.append(dict(inputs))
            if len(calls) == 1:
                raise TimeoutError("provider timeout")
            return {"forecast": {"rain_probability": 0}}

        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"weather.get_forecast": handler}
            ),
            retry_enabled=True,
            sleeper=lambda _: None,
        )
        result = executor.execute(graph, snapshot, report)

        self.assertEqual(ExecutionOutcome.SUCCEEDED, result.summary.outcome)
        self.assertEqual(1, result.summary.retry_count)
        self.assertEqual(2, len(calls))
        self.assertEqual(
            calls[0]["_idempotency_key"],
            calls[1]["_idempotency_key"],
        )
        history = result.session.node_records["weather"].attempt_history
        self.assertEqual(2, len(history))
        self.assertEqual(
            history[0].idempotency_key, history[1].idempotency_key
        )

    def test_provider_fallback_flag_is_used_only_for_safe_read(self):
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "Any")},
            retry_policy=RetryPolicy(
                max_attempts=2,
                provider_fallback_allowed=True,
            ),
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        calls = []

        def handler(inputs):
            calls.append(dict(inputs))
            if len(calls) == 1:
                raise TimeoutError("timeout")
            return {"forecast": "fallback"}

        result = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"weather.get_forecast": handler}
            ),
            retry_enabled=True,
            sleeper=lambda _: None,
        ).execute(graph, snapshot, report)

        self.assertEqual(ExecutionOutcome.SUCCEEDED, result.summary.outcome)
        self.assertFalse(calls[0]["_use_fallback_provider"])
        self.assertTrue(calls[1]["_use_fallback_provider"])

    def test_feature_flags_fail_closed_when_retry_and_replan_are_off(self):
        node = TaskNode(
            "search",
            NodeType.CAPABILITY,
            "contacts.search",
            "search",
            outputs={"contacts": OutputDefinition("contacts", "Any")},
            retry_policy=RetryPolicy(max_attempts=3),
            verification_policy=VerificationPolicy(
                VerificationLevel.SEMANTIC
            ),
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        calls = []
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "contacts.search": lambda _: calls.append(1)
                    or {"contacts": []}
                }
            ),
            retry_enabled=False,
            replan_enabled=False,
        )

        result = executor.execute(graph, snapshot, report)

        self.assertEqual(1, len(calls))
        self.assertFalse(result.requires_replan)
        self.assertEqual(
            ExecutionOutcome.VERIFICATION_FAILED,
            result.summary.outcome,
        )

    def test_mail_sent_state_semantic_verification(self):
        node = TaskNode(
            "mail",
            NodeType.CAPABILITY,
            "mail.send",
            "send",
            outputs={"message": OutputDefinition("message", "Any")},
            verification_policy=VerificationPolicy(
                VerificationLevel.SEMANTIC
            ),
        )
        verifier = NodeResultVerifier()

        passed = verifier.verify(
            node,
            {},
            {"message": {"messageId": "m-1", "status": "sent"}},
        )
        failed = verifier.verify(
            node,
            {},
            {"message": {"messageId": "m-1", "status": "draft"}},
        )

        self.assertEqual(VerificationStatus.PASSED, passed.status)
        self.assertEqual(VerificationStatus.FAILED, failed.status)

    def test_retry_exhausted_and_checkpoint_history_restore(self):
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "Any")},
            retry_policy=RetryPolicy(max_attempts=2),
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "weather.get_forecast": lambda _: (_ for _ in ()).throw(
                        TimeoutError("timeout")
                    )
                }
            ),
            retry_enabled=True,
            sleeper=lambda _: None,
        )
        result = executor.execute(graph, snapshot, report)
        checkpoint = result.session.to_checkpoint()
        restored = GraphExecutionSession.from_checkpoint(
            checkpoint, graph, snapshot
        )

        self.assertEqual(
            ExecutionOutcome.RETRY_EXHAUSTED, result.summary.outcome
        )
        self.assertEqual(
            2, len(restored.node_records["weather"].attempt_history)
        )
        self.assertEqual(
            result.session.node_records["weather"].idempotency_key,
            restored.node_records["weather"].idempotency_key,
        )

    def test_waiting_for_retry_checkpoint_restores(self):
        node = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "Any")},
        )
        graph = graph_for(node)
        snapshot, _ = validated_snapshot(graph)
        session = GraphExecutionSession.create(graph, snapshot)
        session.state = GraphExecutionState.WAITING_FOR_RETRY
        session.set_waiting_reason(
            ExecutionWaitingReason.WAITING_FOR_RETRY,
            node_id="weather",
        )

        restored = GraphExecutionSession.from_checkpoint(
            session.to_checkpoint(), graph, snapshot
        )

        self.assertEqual(
            ExecutionWaitingReason.WAITING_FOR_RETRY,
            restored.waiting_reason,
        )
        self.assertEqual(session.waiting_since, restored.waiting_since)

    def test_goal_verification_required_criterion(self):
        criterion = SuccessCriterion("result required")
        goal = GoalSpecification(
            "goal-reliable",
            "test",
            "test",
            success_criteria=(criterion,),
        )
        node = TaskNode(
            "result",
            NodeType.RESULT,
            "",
            "",
            inputs={"message": literal("ok")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(CapabilityExecutionAdapter())
        mapping = SuccessCriterionMapping(
            criterion.criterion_id,
            "result",
            "result",
            VerificationLevel.SCHEMA,
        )

        passed = executor.execute(
            graph,
            snapshot,
            report,
            goal=goal,
            success_criteria_mappings=(mapping,),
        )

        self.assertEqual(ExecutionOutcome.SUCCEEDED, passed.summary.outcome)
        self.assertEqual(
            VerificationStatus.PASSED,
            passed.summary.goal_verification_status,
        )

    def test_recovery_uses_readback_for_interrupted_mutation(self):
        node = TaskNode(
            "update",
            NodeType.CAPABILITY,
            "calendar.update_event",
            "update_event",
            outputs={"event": OutputDefinition("event", "CalendarEvent")},
            permission_requirement=PermissionRequirement.CONFIRM_REQUIRED,
        )
        graph = graph_for(node)
        snapshot, _ = validated_snapshot(graph)
        session = GraphExecutionSession.create(graph, snapshot)
        session.node_records["update"].state = (
            session.node_records["update"].state.RUNNING
        )

        actions = RecoveryController().recover(session, graph)

        self.assertEqual("ReadBack", actions["update"])

    def test_restart_readback_avoids_duplicate_mutation(self):
        node = TaskNode(
            "update",
            NodeType.CAPABILITY,
            "calendar.update_event",
            "update_event",
            inputs={"time": literal("16:00")},
            outputs={"event": OutputDefinition("event", "CalendarEvent")},
            permission_requirement=PermissionRequirement.CONFIRM_REQUIRED,
            verification_policy=VerificationPolicy(
                VerificationLevel.EXTERNAL_READ_BACK,
                read_back_capability_id="calendar.get_event",
            ),
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        session = GraphExecutionSession.create(graph, snapshot)
        record = session.node_records["update"]
        record.state = record.state.RUNNING
        record.resolved_inputs = {"time": "16:00"}
        mutation_calls = []
        readback_calls = []
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "calendar.update_event": lambda values: mutation_calls.append(
                        values
                    ),
                    "calendar.get_event": lambda values: readback_calls.append(
                        values
                    )
                    or {"event": {"start_time": "16:00"}},
                }
            )
        )

        result = executor.execute(
            graph, snapshot, report, session=session
        )

        self.assertEqual(ExecutionOutcome.SUCCEEDED, result.summary.outcome)
        self.assertEqual([], mutation_calls)
        self.assertEqual(1, len(readback_calls))
        self.assertIn("update:ReadBack", result.summary.recovery_path)

    def test_not_found_requests_partial_replan(self):
        node = TaskNode(
            "search",
            NodeType.CAPABILITY,
            "contacts.search",
            "search",
            outputs={"contacts": OutputDefinition("contacts", "Any")},
            verification_policy=VerificationPolicy(
                VerificationLevel.SEMANTIC
            ),
        )
        graph = graph_for(node)
        snapshot, report = validated_snapshot(graph)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"contacts.search": lambda _: {"contacts": []}}
            ),
            replan_enabled=True,
        )

        result = executor.execute(graph, snapshot, report)

        self.assertTrue(result.requires_replan)
        self.assertEqual(
            ErrorCategory.NOT_FOUND,
            result.replan_trigger.failure_category,
        )
        self.assertEqual("target_not_found", result.replan_trigger.reason)

    def test_partial_replan_creates_new_graph_and_session_lineage(self):
        completed = TaskNode(
            "weather",
            NodeType.CAPABILITY,
            "weather.get_forecast",
            "get_forecast",
            outputs={"forecast": OutputDefinition("forecast", "Any")},
        )
        current_graph = graph_for(completed)
        current_snapshot, _ = validated_snapshot(current_graph)
        current_session = GraphExecutionSession.create(
            current_graph, current_snapshot
        )
        current_session.node_records["weather"].state = (
            current_session.node_records["weather"].state.SUCCEEDED
        )
        current_session.output_store.put(
            TypedOutput(
                "weather",
                "forecast",
                "Any",
                {"rain_probability": 80},
            )
        )
        trigger = ReplanTrigger.from_failure(
            node_id="missing",
            category=ErrorCategory.NOT_FOUND,
            session=current_session,
        )
        replacement = TaskNode(
            "result",
            NodeType.RESULT,
            "",
            "",
            inputs={"message": literal("replanned")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        replacement_graph = NativeTaskGraph(
            current_graph.graph_id,
            current_graph.goal_id,
            current_graph.conversation_id,
            nodes=(replacement,),
            outputs=(
                GraphOutput(
                    "result", "result", "result", "string", is_primary=True
                ),
            ),
            metadata=metadata(),
        )

        @dataclass(frozen=True)
        class FakePlannerResult:
            status: object
            graph: object

        planner = lambda _: FakePlannerResult(
            PlannerStatus.PLANNED, replacement_graph
        )
        validator = SimpleNamespace(
            validate=lambda *args, **kwargs: SimpleNamespace(is_valid=True)
        )
        snapshot_factory = SimpleNamespace(
            create=lambda *args, **kwargs: SimpleNamespace(
                snapshot_id="replan-snapshot"
            )
        )
        controller = ReplanController(
            planner,
            validator=validator,
            snapshot_factory=snapshot_factory,
        )
        decision = controller.build_request(
            goal=None,
            graph=current_graph,
            snapshot=current_snapshot,
            session=current_session,
            trigger=trigger,
            capability_snapshot=SimpleNamespace(),
        )

        result = controller.replan(decision)

        self.assertTrue(result.succeeded)
        self.assertNotEqual(current_graph.graph_id, result.graph.graph_id)
        self.assertEqual(
            current_graph.graph_id, result.graph.metadata["parentGraphId"]
        )
        self.assertEqual(
            current_graph.version,
            result.graph.metadata["previousGraphVersion"],
        )
        self.assertEqual(
            current_session.goal_execution_id,
            result.session.goal_execution_id,
        )
        self.assertIn(
            current_session.session_id, result.session.previous_session_ids
        )
        self.assertEqual(
            {"rain_probability": 80},
            result.binding_context["previous_results"]["forecast"],
        )

    def test_optional_goal_failure_can_complete_partial(self):
        required = SuccessCriterion("required")
        optional = SuccessCriterion("optional", required=False)
        goal = GoalSpecification(
            "goal-reliable",
            "test",
            "test",
            success_criteria=(required, optional),
        )
        node = TaskNode(
            "result",
            NodeType.RESULT,
            "",
            "",
            inputs={"message": literal("ok")},
            outputs={"result": OutputDefinition("result", "string")},
        )
        graph = replace(
            graph_for(node),
            execution_policy=GraphExecutionPolicy(
                allow_partial_completion=True
            ),
        )
        snapshot, report = validated_snapshot(graph)
        mappings = (
            SuccessCriterionMapping(
                required.criterion_id,
                "result",
                "result",
                VerificationLevel.SCHEMA,
            ),
            SuccessCriterionMapping(
                optional.criterion_id,
                "result",
                "missing",
                VerificationLevel.SCHEMA,
            ),
        )
        result = GraphExecutor(CapabilityExecutionAdapter()).execute(
            graph,
            snapshot,
            report,
            goal=goal,
            success_criteria_mappings=mappings,
        )

        self.assertEqual(ExecutionOutcome.PARTIAL, result.summary.outcome)
        self.assertEqual(
            VerificationStatus.INCONCLUSIVE,
            result.summary.goal_verification_status,
        )


if __name__ == "__main__":
    unittest.main()
