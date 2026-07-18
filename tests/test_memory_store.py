import unittest
from pathlib import Path

from jarvis.config.loader import create_config_from_dict
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.memory_store import InMemoryStore, JsonMemoryStore, MemoryCategory, MemoryManager


class TestMemoryStore(unittest.TestCase):
    """Test long-term memory store behavior."""

    def test_memory_manager_creates_structured_memory(self):
        """Check that stored memories include metadata."""
        manager = MemoryManager(store=InMemoryStore())

        memory = manager.remember(
            "Owner prefers pyttsx3 as the default TTS.",
            title="Default TTS Preference",
            category=MemoryCategory.PREFERENCE,
            source="test",
            tags=["voice", "tts"],
        )

        self.assertIsNotNone(memory.id)
        self.assertEqual(memory.title, "Default TTS Preference")
        self.assertEqual(memory.category, MemoryCategory.PREFERENCE)
        self.assertEqual(memory.source, "test")
        self.assertIn("voice", memory.tags)
        self.assertNotEqual(memory.created_at, "")
        self.assertNotEqual(memory.updated_at, "")

    def test_memory_store_retrieval_apis(self):
        """Check metadata-based retrieval APIs."""
        manager = MemoryManager(store=InMemoryStore())
        manager.remember("Jarvis targets v0.3.0 Beta.", title="Jarvis Beta", category="project", tags=["jarvis"])
        manager.remember("Owner studies Japanese N4.", title="Japanese Study", category="goal", tags=["japanese"])

        self.assertEqual(len(manager.find_by_category("project")), 1)
        self.assertEqual(len(manager.find_by_tag("japanese")), 1)
        self.assertEqual(len(manager.search("beta")), 1)
        self.assertEqual(len(manager.search("study")), 1)
        self.assertEqual(len(manager.find_recent(limit=1)), 1)

    def test_memory_manager_updates_and_deletes_memory(self):
        """Check update and delete operations."""
        manager = MemoryManager(store=InMemoryStore())
        memory = manager.remember("Old content", category="fact")

        updated = manager.update(memory.id, content="New content", title="New title", tags=["updated"])
        deleted = manager.delete(memory.id)

        self.assertEqual(updated.content, "New content")
        self.assertEqual(updated.title, "New title")
        self.assertIn("updated", updated.tags)
        self.assertTrue(deleted)
        self.assertIsNone(manager.get(memory.id))

    def test_json_memory_store_persists_across_instances(self):
        """Check JSON-backed memory persists across manager instances."""
        tmp_root = Path("tmp") / "tests"
        tmp_root.mkdir(parents=True, exist_ok=True)

        path = tmp_root / "memory_store_persistence_test.json"

        try:
            if path.exists():
                path.unlink()

            first_manager = MemoryManager(store=JsonMemoryStore(path))
            first_manager.load()
            first_manager.remember("Persistent memory.", title="Persistent Title", category="fact", tags=["persist"])

            second_manager = MemoryManager(store=JsonMemoryStore(path))
            loaded = second_manager.load()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].title, "Persistent Title")
            self.assertEqual(loaded[0].content, "Persistent memory.")
            self.assertEqual(loaded[0].category, MemoryCategory.FACT)
        finally:
            if path.exists():
                path.unlink()

    def test_memory_diagnostics_events(self):
        """Check memory lifecycle diagnostics events."""
        diagnostics = DiagnosticsCollector()
        manager = MemoryManager(
            store=InMemoryStore(),
            diagnostics_collector=diagnostics,
        )

        manager.load()
        memory = manager.remember("Diagnostic memory.", category="fact")
        manager.find_recent()
        manager.update(memory.id, content="Updated diagnostic memory.")
        manager.delete(memory.id)

        messages = [event.message for event in diagnostics.get_snapshot().events]
        self.assertIn("memory.loaded", messages)
        self.assertIn("memory.created", messages)
        self.assertIn("memory.retrieved", messages)
        self.assertIn("memory.updated", messages)
        self.assertIn("memory.deleted", messages)

    def test_blank_memory_is_ignored(self):
        """Check manager decides when to ignore empty content."""
        manager = MemoryManager(store=InMemoryStore())

        memory = manager.remember("   ")

        self.assertIsNone(memory)
        self.assertEqual(manager.find_recent(), [])

    def test_config_sets_memory_store_path(self):
        """Check config can choose the memory store path."""
        config = create_config_from_dict(
            {
                "memory_store": {
                    "path": "tmp/test_memory_store.json",
                }
            }
        )

        self.assertEqual(config.memory_store.path, "tmp/test_memory_store.json")


if __name__ == "__main__":
    unittest.main()
