import unittest

from jarvis.core.todos import TODO_ACTIVE, TODO_CANCELLED, TODO_COMPLETED, TodoRepository


class TodoRepositoryTest(unittest.TestCase):
    def test_create_update_complete_delete_restore_history(self):
        repository = TodoRepository()

        todo = repository.create("우유 사기", due_at="2026-07-18T17:00:00")
        self.assertEqual(todo.status, TODO_ACTIVE)
        self.assertEqual(todo.revision, 1)
        self.assertEqual(len(repository.history(todo.id)), 1)
        self.assertEqual(repository.events[-1].event_type, "TodoCreated")

        updated = repository.update(todo.id, title="우유와 빵 사기")
        self.assertEqual(updated.title, "우유와 빵 사기")
        self.assertEqual(updated.revision, 2)
        self.assertEqual(repository.events[-1].event_type, "TodoUpdated")

        completed = repository.complete(todo.id)
        self.assertEqual(completed.status, TODO_COMPLETED)
        self.assertTrue(completed.completed_at)
        self.assertEqual(repository.events[-1].event_type, "TodoCompleted")

        deleted = repository.delete(todo.id)
        self.assertEqual(deleted.status, TODO_CANCELLED)
        self.assertEqual(repository.events[-1].event_type, "TodoDeleted")

        restored = repository.restore(todo.id)
        self.assertEqual(restored.status, TODO_ACTIVE)
        self.assertEqual(repository.events[-1].event_type, "TodoRestored")
        self.assertGreaterEqual(len(repository.history(todo.id)), 5)

    def test_list_filters_by_status_and_date_scope(self):
        repository = TodoRepository()
        today = repository.create("오늘 할 일")
        tomorrow = repository.create("내일 할 일", due_at="2999-01-01T09:00:00")
        repository.complete(today.id)

        active = repository.list(status=TODO_ACTIVE)
        self.assertIn(tomorrow, active)
        self.assertNotIn(today, active)

        completed = repository.list(status=TODO_COMPLETED)
        self.assertIn(repository.find(today.id), completed)


if __name__ == "__main__":
    unittest.main()
