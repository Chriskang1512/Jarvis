import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path

from jarvis.core.events import InMemoryEventBus
from jarvis.execution_memory import (
    CURRENT_EXECUTION_MEMORY_SCHEMA_VERSION,
    CURRENT_SQLITE_SCHEMA_VERSION,
    ExecutionMemoryService,
    HistoryType,
    InMemoryExecutionMemoryRepository,
    KeywordSemanticSearchProvider,
    MemoryRedactor,
    PlannerHint,
    SQLiteExecutionMemoryRepository,
)
from jarvis.graph_execution import CapabilityExecutionAdapter, GraphExecutor
from jarvis.graph_execution import ErrorCategory
from jarvis.graph_execution.reliability import (
    AttemptRecord,
    VerificationStatus,
)
from jarvis.native_task_graph import (
    GraphOutput,
    NativeTaskGraph,
    NodeType,
    OutputDefinition,
    TaskNode,
    VerificationLevel,
    VerificationPolicy,
)
from tests.test_graph_executor_runtime import metadata, validated_snapshot


class AlternateSearchProvider:
    provider_name = "alternate"

    def search(self, query, records, limit=10):
        return KeywordSemanticSearchProvider().search(
            query, records, limit=limit
        )


class EventCollector:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)


class FailingMemoryRepository(InMemoryExecutionMemoryRepository):
    def add(self, record):
        raise OSError("simulated persistence failure")


def execution_graph():
    node = TaskNode(
        "weather",
        NodeType.CAPABILITY,
        "weather.get_forecast",
        "get_forecast",
        outputs={
            "forecast": OutputDefinition("forecast", "WeatherReport")
        },
        verification_policy=VerificationPolicy(
            VerificationLevel.SEMANTIC
        ),
    )
    return NativeTaskGraph(
        "graph-memory",
        "goal-memory",
        "conversation-memory",
        nodes=(node,),
        outputs=(
            GraphOutput(
                "forecast",
                node.node_id,
                "forecast",
                "WeatherReport",
                is_primary=True,
            ),
        ),
        metadata=metadata(),
    )


class TestExecutionMemory(unittest.TestCase):
    def execute(self, repository=None, event_bus=None):
        graph = execution_graph()
        snapshot, report = validated_snapshot(graph)
        repository = repository or InMemoryExecutionMemoryRepository()
        memory = ExecutionMemoryService(repository)
        executor = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={
                    "weather.get_forecast": lambda _: {
                        "forecast": {
                            "location": "Gangneung",
                            "condition": "clear",
                        }
                    }
                }
            ),
            event_bus=event_bus,
            execution_memory=memory,
        )
        result = executor.execute(graph, snapshot, report)
        return graph, result, memory, repository

    def test_execution_summary_is_immutable_and_record_is_versioned(self):
        graph, result, memory, repository = self.execute()
        record = repository.get_by_execution(result.session.session_id)

        self.assertEqual(
            CURRENT_EXECUTION_MEMORY_SCHEMA_VERSION,
            record.schema_version,
        )
        self.assertEqual(result.summary.result_hash, record.result_hash)
        self.assertEqual(graph.goal_id, record.goal_id)
        with self.assertRaises(FrozenInstanceError):
            result.summary.result_hash = "changed"
        with self.assertRaises(FrozenInstanceError):
            record.outcome = "changed"

    def test_duplicate_summary_is_idempotent(self):
        graph, result, memory, repository = self.execute()

        existing, created = memory.remember(
            result.summary,
            graph=graph,
            session=result.session,
        )

        self.assertFalse(created)
        self.assertEqual(1, len(repository.list()))
        self.assertEqual(
            result.session.session_id,
            existing.source_execution_id,
        )

    def test_redactor_removes_nested_secrets_and_personal_values(self):
        redacted = MemoryRedactor().redact(
            {
                "accessToken": "secret",
                "mail_body": "private body",
                "nested": {
                    "contacts": [{"email": "aya@example.com"}],
                    "safe": "call +82 10-1234-5678",
                },
            }
        )

        self.assertEqual("[REDACTED]", redacted["accessToken"])
        self.assertEqual("[REDACTED]", redacted["mail_body"])
        self.assertEqual("[REDACTED]", redacted["nested"]["contacts"])
        self.assertNotIn(
            "10-1234-5678", redacted["nested"]["safe"]
        )
        allowlisted = MemoryRedactor().redact_allowlisted(
            {
                "durationSeconds": 1.5,
                "futureSummaryField": "must not persist",
            },
            {"durationSeconds"},
        )
        self.assertEqual({"durationSeconds": 1.5}, allowlisted)

    def test_search_supports_metadata_semantic_and_provider_replacement(self):
        _, result, memory, repository = self.execute()

        keyword = memory.search.keyword("weather")
        semantic = memory.search.semantic("weather")
        alternate = ExecutionMemoryService(
            repository,
            semantic_provider=AlternateSearchProvider(),
        ).search.semantic("weather")

        self.assertEqual(result.session.session_id, keyword[0].session_id)
        self.assertEqual(result.session.session_id, semantic[0].record.session_id)
        self.assertEqual(
            result.session.session_id,
            alternate[0].record.session_id,
        )
        self.assertEqual("Passed", semantic[0].verification_status)
        self.assertEqual(
            result.session.session_id,
            semantic[0].provenance.source_execution_id,
        )

    def test_history_and_replay_are_references_not_event_copies(self):
        _, result, memory, repository = self.execute()
        record = repository.get_by_execution(result.session.session_id)

        self.assertTrue(
            any(
                item.history_type == HistoryType.EXECUTION
                for item in record.histories
            )
        )
        self.assertTrue(
            any(
                item.history_type == HistoryType.VERIFICATION
                for item in record.histories
            )
        )
        self.assertTrue(record.replay_reference.available)
        self.assertTrue(
            record.replay_reference.journal_reference.startswith(
                "checkpoint://"
            )
        )
        self.assertFalse(
            any(
                key in record.redacted_metadata
                for key in ("events", "timeline", "transcript")
            )
        )

    def test_sqlite_round_trip_and_duplicate_rejection(self):
        path = Path("tmp") / "tests" / "execution_memory.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        candidates = (
            path,
            path.with_name(path.name + "-wal"),
            path.with_name(path.name + "-shm"),
        )
        for candidate in candidates:
            if candidate.exists():
                candidate.unlink()
        try:
            repository = SQLiteExecutionMemoryRepository(path)
            graph, result, memory, _ = self.execute(repository)

            restored = repository.get_by_execution(
                result.session.session_id
            )
            _, created = memory.remember(
                result.summary,
                graph=graph,
                session=result.session,
            )

            self.assertEqual(result.summary.result_hash, restored.result_hash)
            self.assertFalse(created)
            self.assertEqual(1, len(repository.list()))
            with repository.session() as connection:
                version = connection.execute(
                    "SELECT version "
                    "FROM execution_memory_schema_versions "
                    "WHERE component = 'execution_memory'"
                ).fetchone()[0]
            self.assertEqual(CURRENT_SQLITE_SCHEMA_VERSION, version)
            with repository.session() as connection:
                connection.execute(
                    "UPDATE execution_memory_schema_versions "
                    "SET version = 999 "
                    "WHERE component = 'execution_memory'"
                )
            with self.assertRaises(RuntimeError):
                SQLiteExecutionMemoryRepository(path)
        finally:
            for candidate in candidates:
                if candidate.exists():
                    candidate.unlink()

    def test_memory_saved_event_and_planner_hint_contract_only(self):
        collector = EventCollector()
        bus = InMemoryEventBus()
        bus.subscribe("*", collector.handle)

        _, result, _, _ = self.execute(event_bus=bus)
        hint = PlannerHint(
            "hint-1",
            "query-goal",
            ("memory-1",),
            "SimilarGoal",
            "Verified prior weather execution",
            required_revalidation=(
                "PROVIDER_AVAILABLE",
                "EXTERNAL_STATE",
            ),
        )

        self.assertTrue(
            any(
                event.event_type == "runtime.execution.memory_saved"
                for event in collector.events
            )
        )
        self.assertEqual("query-goal", hint.query_goal_id)
        self.assertFalse(hasattr(result, "planner_hint"))

    def test_memory_failure_is_observable_without_changing_execution(self):
        collector = EventCollector()
        bus = InMemoryEventBus()
        bus.subscribe("*", collector.handle)

        _, result, _, _ = self.execute(
            repository=FailingMemoryRepository(),
            event_bus=bus,
        )

        self.assertEqual("Succeeded", result.summary.outcome.value)
        failures = [
            event
            for event in collector.events
            if event.event_type == "execution_memory.persist.failure"
        ]
        self.assertEqual(1, len(failures))
        self.assertEqual("OSError", failures[0].payload["error_type"])

    def test_retry_replan_permission_and_failure_histories_are_queryable(self):
        graph, result, memory, _ = self.execute()
        node = result.session.node_records["weather"]
        node.attempt_history.append(
            AttemptRecord(
                2,
                "mock",
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
                0.01,
                "Failed",
                ErrorCategory.TIMEOUT,
                "timeout",
                True,
                VerificationStatus.FAILED,
                "stable-key",
                "",
            )
        )
        node.error = ErrorCategory.TIMEOUT.value
        result.session.append_timeline(
            "permission_required", "weather"
        )
        summary = replace(
            result.summary,
            retry_count=1,
            replan_count=1,
        )

        record = memory.to_record(
            summary,
            graph=graph,
            session=result.session,
        )
        types = {item.history_type for item in record.histories}

        self.assertIn(HistoryType.RETRY, types)
        self.assertIn(HistoryType.REPLAN, types)
        self.assertIn(HistoryType.PERMISSION, types)
        self.assertIn(HistoryType.FAILURE, types)
        permission = next(
            item
            for item in record.histories
            if item.history_type == HistoryType.PERMISSION
        )
        self.assertEqual("requested", permission.status)
        self.assertEqual(
            "weather.get_forecast", permission.metadata["scope"]
        )
        self.assertEqual(
            {"scope", "reason"}, set(permission.metadata)
        )


if __name__ == "__main__":
    unittest.main()
