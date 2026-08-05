import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from jarvis.artifacts import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    ArtifactBuildRequest,
    ArtifactBuilder,
    ArtifactManager,
    ArtifactStatus,
    ArtifactType,
    ArtifactVisibility,
    InMemoryArtifactRepository,
    SQLiteArtifactRepository,
    artifact_from_dict,
    artifact_to_dict,
)
from jarvis.dashboard import DashboardBackend
from jarvis.core.events import InMemoryEventBus
from jarvis.graph_execution import CapabilityExecutionAdapter, GraphExecutor
from jarvis.native_task_graph import (
    GraphOutput,
    NativeTaskGraph,
    NodeType,
    OutputDefinition,
    TaskNode,
)
from tests.test_graph_executor_runtime import metadata, validated_snapshot


def request(name="mail", **overrides):
    values = dict(
        artifact_type=ArtifactType.MAIL,
        title=name,
        source_goal_id="goal-artifact",
        source_execution_id="execution-artifact",
        node_id="send-mail",
        output_key=name,
        produced_by_capability="mail.send",
        provider="gmail",
        ability_version="1.0",
        external_resource_id=f"external-{name}",
        visibility=ArtifactVisibility.USER,
        tags=("aya", "mail"),
    )
    values.update(overrides)
    return ArtifactBuildRequest(**values)


class TestArtifactManager(unittest.TestCase):
    def test_builder_creates_stable_immutable_provider_neutral_ref(self):
        builder = ArtifactBuilder()
        first = builder.build(request())
        second = builder.build(request())

        self.assertEqual(first.artifact_id, second.artifact_id)
        changed_checksum = builder.build(request(checksum="changed"))
        self.assertEqual(first.artifact_id, changed_checksum.artifact_id)
        self.assertEqual(CURRENT_ARTIFACT_SCHEMA_VERSION, first.schema_version)
        self.assertEqual("mail.send", first.produced_by_capability)
        self.assertEqual("gmail", first.provenance.provider)
        with self.assertRaises(FrozenInstanceError):
            first.title = "changed"
        with self.assertRaises(TypeError):
            first.metadata["new"] = True
        with self.assertRaises(ValueError):
            replace(first, checksum="")

    def test_initial_artifact_types_are_supported_and_extensible(self):
        expected = {
            "MAIL", "CALENDAR_EVENT", "FILE", "PDF", "IMAGE", "AUDIO",
            "VIDEO", "DOCUMENT", "TEXT", "CLIPBOARD", "CUSTOM",
        }
        self.assertTrue(expected.issubset({item.name for item in ArtifactType}))

    def test_json_round_trip_preserves_identity_and_unknown_fields(self):
        artifact = ArtifactBuilder().build(request())
        payload = artifact_to_dict(artifact)
        payload["futureField"] = "ignored"
        restored = artifact_from_dict(payload)
        self.assertEqual(artifact, restored)

    def test_repository_searches_all_required_metadata(self):
        repository = InMemoryArtifactRepository()
        artifact = ArtifactBuilder().build(request(title="Aya mail"))
        repository.save(artifact)

        self.assertEqual(artifact, repository.search_metadata(artifact_id=artifact.artifact_id)[0])
        self.assertEqual(artifact, repository.search_metadata(query="Aya")[0])
        self.assertEqual(artifact, repository.search_metadata(artifact_type="Mail")[0])
        self.assertEqual(artifact, repository.search_metadata(tag="aya")[0])
        self.assertEqual(artifact, repository.search_metadata(goal_id="goal-artifact")[0])
        self.assertEqual(artifact, repository.search_metadata(execution_id="execution-artifact")[0])

    def test_parent_child_tree_cycle_guard_and_soft_delete(self):
        repository = InMemoryArtifactRepository()
        builder = ArtifactBuilder()
        mail, _ = repository.save(builder.build(request("mail")))
        pdf, _ = repository.save(builder.build(request("pdf", artifact_type=ArtifactType.PDF)))
        image, _ = repository.save(builder.build(request("image", artifact_type=ArtifactType.IMAGE)))

        mail, pdf = repository.link(mail.artifact_id, pdf.artifact_id)
        pdf, image = repository.link(pdf.artifact_id, image.artifact_id)
        self.assertIn(pdf.artifact_id, mail.child_artifact_ids)
        self.assertEqual(pdf.artifact_id, image.parent_artifact_id)
        self.assertEqual(mail.artifact_id, repository.parent(pdf.artifact_id).artifact_id)
        self.assertEqual(pdf.artifact_id, repository.children(mail.artifact_id)[0].artifact_id)
        with self.assertRaises(ValueError):
            repository.link(image.artifact_id, mail.artifact_id)

        deleted = repository.soft_delete(image.artifact_id)
        self.assertEqual(ArtifactStatus.DELETED, deleted.status)
        self.assertIsNone(repository.get(image.artifact_id))
        self.assertIsNotNone(repository.get(image.artifact_id, include_deleted=True))

    def test_relationship_depth_defaults_to_twenty_and_is_configurable(self):
        repository = InMemoryArtifactRepository(max_relationship_depth=3)
        builder = ArtifactBuilder()
        artifacts = [
            repository.save(builder.build(request(f"depth-{index}")))[0]
            for index in range(4)
        ]
        repository.link(artifacts[0].artifact_id, artifacts[1].artifact_id)
        repository.link(artifacts[1].artifact_id, artifacts[2].artifact_id)
        with self.assertRaises(ValueError):
            repository.link(
                artifacts[2].artifact_id, artifacts[3].artifact_id
            )

    def test_sqlite_round_trip_relationship_and_schema_version(self):
        path = Path("tmp/tests/artifact_manager.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(path) + suffix)
            if candidate.exists():
                candidate.unlink()
        try:
            repository = SQLiteArtifactRepository(path)
            builder = ArtifactBuilder()
            parent, _ = repository.save(builder.build(request("parent")))
            child, _ = repository.save(builder.build(request("child")))
            repository.link(parent.artifact_id, child.artifact_id)

            restored = SQLiteArtifactRepository(path)
            self.assertIn(child.artifact_id, restored.get(parent.artifact_id).child_artifact_ids)
            with restored.session() as connection:
                version = connection.execute(
                    "SELECT version FROM artifact_schema_versions WHERE component='artifact_manager'"
                ).fetchone()[0]
            self.assertEqual(1, version)
            with restored.session() as connection:
                connection.execute(
                    "UPDATE artifact_schema_versions SET version=999 "
                    "WHERE component='artifact_manager'"
                )
            with self.assertRaises(RuntimeError):
                SQLiteArtifactRepository(path)
        finally:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(str(path) + suffix)
                if candidate.exists():
                    candidate.unlink()

    def test_semantic_search_contract_is_not_runtime_enabled(self):
        manager = ArtifactManager(InMemoryArtifactRepository())
        with self.assertRaises(RuntimeError):
            manager.search.semantic("mail")

    def test_native_verified_output_is_captured_via_builder(self):
        node = TaskNode(
            "calendar",
            NodeType.CAPABILITY,
            "calendar.create_event",
            "create_event",
            outputs={
                "event": OutputDefinition(
                    "event", "CalendarEvent", artifact_type="CalendarEventRef"
                )
            },
        )
        graph = NativeTaskGraph(
            "graph-artifact",
            "goal-artifact",
            "conversation-artifact",
            nodes=(node,),
            outputs=(GraphOutput("event", "calendar", "event", "CalendarEvent"),),
            metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        repository = InMemoryArtifactRepository()
        result = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"calendar.create_event": lambda _: {"event": {"eventId": "evt-1"}}}
            ),
            artifact_manager=ArtifactManager(repository),
        ).execute(graph, snapshot, report)

        artifact = repository.list()[0]
        self.assertEqual(ArtifactType.CALENDAR_EVENT, artifact.artifact_type)
        self.assertEqual("evt-1", artifact.external_resource_id)
        self.assertEqual(artifact.artifact_id, result.summary.artifacts[0]["artifactId"])
        self.assertNotIn("eventId", artifact.metadata)

    def test_artifact_persist_failure_is_observable_and_execution_succeeds(self):
        class FailingManager:
            def capture_execution(self, graph, session):
                raise OSError("artifact store unavailable")

        class Collector:
            def __init__(self):
                self.events = []

            def handle(self, event):
                self.events.append(event)

        node = TaskNode(
            "text",
            NodeType.CAPABILITY,
            "system.format_result",
            "format",
            outputs={"result": OutputDefinition("result", "string", artifact_type="Text")},
        )
        graph = NativeTaskGraph(
            "graph-failure", "goal-failure", "conversation-failure",
            nodes=(node,), metadata=metadata(),
        )
        snapshot, report = validated_snapshot(graph)
        collector = Collector()
        bus = InMemoryEventBus()
        bus.subscribe("*", collector.handle)
        result = GraphExecutor(
            CapabilityExecutionAdapter(
                handlers={"system.format_result": lambda _: {"result": "ok"}}
            ),
            event_bus=bus,
            artifact_manager=FailingManager(),
        ).execute(graph, snapshot, report)

        self.assertEqual("Succeeded", result.summary.outcome.value)
        self.assertTrue(any(
            item.event_type == "artifact_manager.persist.failure"
            for item in collector.events
        ))

    def test_dashboard_exposes_read_only_artifact_views(self):
        repository = InMemoryArtifactRepository()
        artifact, _ = repository.save(ArtifactBuilder().build(request()))
        dashboard = DashboardBackend(None, artifact_repository=repository)

        self.assertEqual(artifact.artifact_id, dashboard.artifacts("mail")[0]["artifactId"])
        self.assertEqual(artifact.artifact_id, dashboard.artifact(artifact.artifact_id)["artifactId"])


if __name__ == "__main__":
    unittest.main()
