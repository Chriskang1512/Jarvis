import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from urllib.request import urlopen

from jarvis.dashboard import (
    DashboardBackend,
    DashboardProjectionEngine,
    InMemoryDashboardProjectionRepository,
    ObservabilityHub,
    ProjectionHealthStatus,
    SafeDashboardProjectionHandler,
    SQLiteDashboardProjectionRepository,
)
from jarvis.core.events import BaseEvent
from jarvis.runtime import RuntimeState


class Event:
    def __init__(self, event_type, payload):
        self.event_type = event_type
        self.payload = payload

    def to_dict(self):
        return dict(self.payload)


class TestDashboardRuntimeProjection(unittest.TestCase):
    def test_runtime_state_contract_is_shared_and_complete(self):
        expected = {
            "IDLE", "LISTENING", "THINKING", "PLANNING", "EXECUTING",
            "WAITING_PERMISSION", "VERIFYING", "SPEAKING", "COMPLETED", "FAILED",
        }
        self.assertEqual(expected, {item.name for item in RuntimeState})

    def test_event_sequence_builds_session_node_timeline_and_statuses(self):
        repository = InMemoryDashboardProjectionRepository()
        engine = DashboardProjectionEngine(repository, snapshot_interval=100)
        events = [
            ("runtime.execution.session_created", {"session_id": "s1", "goal_id": "g1"}),
            ("runtime.execution.node_ready", {"session_id": "s1", "node_id": "weather", "capability_id": "weather.get_forecast"}),
            ("runtime.execution.node_started", {"session_id": "s1", "node_id": "weather", "provider_id": "mock"}),
            ("runtime.execution.retry_started", {"session_id": "s1", "node_id": "weather"}),
            ("runtime.execution.permission_requested", {"session_id": "s1", "node_id": "calendar"}),
            ("runtime.execution.permission_resolved", {"session_id": "s1", "node_id": "calendar"}),
            ("runtime.execution.verification_started", {"session_id": "s1", "node_id": "weather"}),
            ("runtime.execution.verification_passed", {"session_id": "s1", "node_id": "weather"}),
            ("runtime.execution.node_completed", {"session_id": "s1", "node_id": "weather"}),
            ("runtime.execution.memory_saved", {"session_id": "s1", "memory_record_id": "m1"}),
            ("runtime.execution.artifacts_captured", {"session_id": "s1", "artifact_ids": ["a1"], "artifacts": [{"artifact_id": "a1", "node_id": "weather"}]}),
            ("runtime.execution.session_completed", {"session_id": "s1", "execution_summary": {"outcome": "Succeeded"}}),
        ]
        for name, payload in events:
            engine.apply(name, payload)

        session = repository.get_session("s1")
        self.assertEqual("Completed", session.status)
        self.assertEqual(RuntimeState.COMPLETED, session.current_runtime_state)
        self.assertEqual("Passed", session.verification_status)
        self.assertEqual("Saved", session.memory_status)
        self.assertEqual("Saved", session.artifact_status)
        self.assertFalse(session.waiting_permission)
        self.assertEqual(1, session.retry_count)
        self.assertEqual(("a1",), session.nodes["weather"].artifact_ids)
        self.assertEqual(list(range(1, 13)), [item.event_sequence for item in session.timeline])
        with self.assertRaises(FrozenInstanceError):
            session.status = "Changed"

    def test_failed_summary_projects_failed_not_completed(self):
        repository = InMemoryDashboardProjectionRepository()
        engine = DashboardProjectionEngine(repository)
        engine.apply("runtime.execution.session_created", {"session_id": "failed"})
        engine.apply(
            "runtime.execution.session_completed",
            {"session_id": "failed", "execution_summary": {"outcome": "VerificationFailed"}},
        )
        self.assertEqual("Failed", repository.get_session("failed").status)

    def test_global_runtime_state_updates_without_session(self):
        engine = DashboardProjectionEngine(InMemoryDashboardProjectionRepository())
        event, session = engine.apply("voice.stt.listening", {})
        self.assertIsNone(session)
        self.assertEqual(RuntimeState.LISTENING, engine.current_runtime_state)
        self.assertEqual(1, event["eventSequence"])

    def test_snapshot_health_and_incremental_events(self):
        repository = InMemoryDashboardProjectionRepository()
        engine = DashboardProjectionEngine(repository, snapshot_interval=2)
        engine.apply("runtime.execution.session_created", {"session_id": "s1"})
        engine.apply("runtime.execution.node_started", {"session_id": "s1", "node_id": "n1"})

        sequence, sessions = repository.latest_snapshot()
        self.assertEqual(2, sequence)
        self.assertEqual("s1", sessions[0].session_id)
        self.assertEqual(ProjectionHealthStatus.HEALTHY, engine.health.status)
        self.assertEqual([2], [item["eventSequence"] for item in repository.events_after(1)])
        repository.reset_sessions()
        self.assertIsNone(repository.get_session("s1"))
        self.assertEqual(2, engine.rebuild())
        self.assertEqual("s1", repository.get_session("s1").session_id)
        self.assertEqual(ProjectionHealthStatus.HEALTHY, engine.health.status)

    def test_projection_failure_isolated_from_runtime(self):
        class FailingRepository(InMemoryDashboardProjectionRepository):
            def append_event(self, event):
                raise OSError("projection unavailable")

        engine = DashboardProjectionEngine(FailingRepository())
        handler = SafeDashboardProjectionHandler(engine)
        result = handler.handle_event(Event("runtime.execution.session_created", {"session_id": "s1"}))

        self.assertIsNone(result)
        self.assertEqual(1, handler.failure_count)
        self.assertEqual(ProjectionHealthStatus.FAILED, engine.health.status)

    def test_core_event_envelope_is_projected_from_nested_payload(self):
        repository = InMemoryDashboardProjectionRepository()
        engine = DashboardProjectionEngine(repository)
        handler = SafeDashboardProjectionHandler(engine)
        handler.handle_event(
            BaseEvent(
                "runtime.execution.session_created",
                "GraphExecutionSession",
                "s-core",
                payload={"session_id": "s-core", "goal_id": "g-core"},
            )
        )

        session = repository.get_session("s-core")
        self.assertEqual("g-core", session.goal)
        self.assertEqual("Running", session.status)

    def test_sqlite_projection_restores_sessions_events_and_snapshot(self):
        path = Path("tmp/tests/dashboard_projection.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        try:
            repository = SQLiteDashboardProjectionRepository(path)
            engine = DashboardProjectionEngine(repository, snapshot_interval=1)
            engine.apply("runtime.execution.session_created", {"session_id": "s1"})
            restored = SQLiteDashboardProjectionRepository(path)
            self.assertEqual("s1", restored.get_session("s1").session_id)
            self.assertEqual(1, restored.events_after(0)[0]["eventSequence"])
            self.assertEqual(1, restored.latest_snapshot()[0])
        finally:
            for suffix in ("", "-wal", "-shm"):
                Path(str(path) + suffix).unlink(missing_ok=True)

    def test_rest_and_websocket_projection_push(self):
        repository = InMemoryDashboardProjectionRepository()
        engine = DashboardProjectionEngine(repository)
        hub = ObservabilityHub()
        queue = hub.subscribe()
        handler = SafeDashboardProjectionHandler(engine, publish=hub.publish_projection)
        handler.handle_event(Event("runtime.execution.session_created", {"session_id": "s1", "goal_id": "weather"}))
        message = queue.get(timeout=1)
        self.assertEqual("dashboard.projection", message["kind"])

        backend = DashboardBackend(
            hub, projection_repository=repository,
            projection_engine=engine, port=0,
        ).start()
        try:
            def get(path):
                with urlopen(backend.url + path, timeout=2) as response:
                    return json.loads(response.read().decode("utf-8"))

            self.assertEqual("s1", get("/api/runtime/sessions/running")[0]["sessionId"])
            self.assertEqual("s1", get("/api/runtime/sessions/recent")[0]["sessionId"])
            self.assertEqual("s1", get("/api/runtime/sessions/s1")["sessionId"])
            self.assertEqual(1, len(get("/api/runtime/sessions/s1/timeline")))
            self.assertEqual(1, get("/api/runtime/statistics")["running"])
            self.assertEqual("Healthy", get("/api/runtime/projection-health")["status"])
        finally:
            backend.stop()

    def test_observability_events_receive_monotonic_sequence(self):
        hub = ObservabilityHub()
        first = hub.record("PlannerStarted")
        second = hub.record("GraphBuilt")
        self.assertEqual(1, first["eventSequence"])
        self.assertEqual(2, second["eventSequence"])

    def test_operator_dashboard_exposes_live_runtime_read_model(self):
        static = Path(__file__).parents[1] / "jarvis" / "dashboard" / "static"
        html = (static / "index.html").read_text(encoding="utf-8")
        script = (static / "app.js").read_text(encoding="utf-8")
        stylesheet = (static / "observability.css").read_text(encoding="utf-8")

        for element_id in (
            "ops-runtime-state", "ops-heading", "ops-elapsed", "ops-permission",
            "ops-graph", "ops-stage-strip", "ops-recent", "ops-timeline",
            "ops-memory", "ops-artifacts", "ops-memory-recent",
            "ops-artifact-recent",
            "ops-ability-health", "ops-health-summary",
            "ops-jarvis-status", "ops-ai-provider", "ops-latency", "ops-tts",
            "ops-stt", "ops-wake", "ops-gpu", "brand-runtime",
            "brand-runtime-state", "runtime-nav", "runtime-nav-beacon",
            "runtime-sound-toggle", "runtime-sound-test",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("function renderOperatorHome()", script)
        self.assertIn("state.projectionSessions", script)
        self.assertIn('msg.kind==="dashboard.projection"', script)
        self.assertIn(".ops-command", stylesheet)
        self.assertIn(".ops-permission[hidden]", stylesheet)
        self.assertIn(".ops-state-mark.state-thinking", stylesheet)
        self.assertIn("function friendlyEvent", script)
        self.assertIn("function renderOperatorHealth", script)
        self.assertIn("normalizedServiceState", script)
        self.assertIn("function renderJarvisStatus", script)
        self.assertIn("function runtimePresentation", script)
        self.assertIn("function observedRuntimeState", script)
        self.assertIn("Thinking about the best plan", script)
        self.assertIn("Listening for your command", script)
        self.assertIn("function playRuntimeSound", script)
        self.assertIn("lastAudibleRuntimeState", script)
        self.assertIn("session.currentRuntimeState", script)
        self.assertIn("runtimeAudioContext.state", script)
        self.assertIn("prefers-reduced-motion", stylesheet)
        guideline = (Path(__file__).parents[1] / "docs" / "runtime-motion-design-guideline.md").read_text(encoding="utf-8")
        self.assertIn("WaitingPermission", guideline)
        self.assertIn("persistent mute control", guideline)
        self.assertIn("eventSequence", script)
        self.assertNotIn("state.runtime.voice||\"Idle\"", script)
        self.assertNotIn("new EventSource", script)


if __name__ == "__main__":
    unittest.main()
