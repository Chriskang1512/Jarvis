import unittest

from jarvis.abilities.native.todo import TodoAbility, TodoIntentParser
from jarvis.core.todos import TODO_ACTIVE, TODO_CANCELLED, TODO_COMPLETED, TodoRepository


class TodoAbilityTest(unittest.TestCase):
    def test_create_requires_confirmation_then_creates(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)

        pending = ability.execute({"text": "우유 사기 추가해"})
        self.assertTrue(pending.success)
        self.assertTrue(pending.data.requires_confirmation)
        self.assertEqual(pending.metadata["permission"], "confirm_required")

        confirmed = ability.execute({"text": "우유 사기 추가해", "_confirmed": True})
        self.assertTrue(confirmed.success)
        self.assertEqual(confirmed.data.action, "create")
        self.assertEqual(confirmed.data.todo.title, "우유 사기")
        self.assertEqual(confirmed.data.todo.status, TODO_ACTIVE)
        self.assertEqual(repository.events[-1].event_type, "TodoCreated")

    def test_list_complete_and_delete(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        first = repository.create("우유 사기")
        second = repository.create("장보기 우유")

        listed = ability.execute({"text": "오늘 할 일 알려줘"})
        self.assertTrue(listed.success)
        self.assertGreaterEqual(len(listed.data.todos), 2)

        compact_listed = ability.execute({"text": "\ud560\uc77c \uc54c\ub824\uc918"})
        self.assertTrue(compact_listed.success)
        self.assertEqual(compact_listed.data.action, "list")

        completed = ability.execute({"text": "첫 번째 완료했어", "_confirmed": True})
        self.assertTrue(completed.success)
        self.assertEqual(repository.find(first.id).status, TODO_COMPLETED)

        deleted = ability.execute({"text": "장보기에서 우유 삭제해", "_confirmed": True})
        self.assertTrue(deleted.success)
        self.assertEqual(repository.find(second.id).status, TODO_CANCELLED)

    def test_generic_delete_uses_first_active_todo(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        todo = repository.create("우유 사기")

        deleted = ability.execute({"text": "할 일 삭제해", "_confirmed": True})

        self.assertTrue(deleted.success)
        self.assertEqual(repository.find(todo.id).status, TODO_CANCELLED)

    def test_delete_completed_todos_deletes_only_completed_items(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        active = repository.create("우유")
        completed_one = repository.complete(repository.create("고기").id)
        completed_two = repository.complete(repository.create("만두").id)

        pending = ability.execute({"text": "완료된 할 일 삭제해"})
        self.assertTrue(pending.success)
        self.assertTrue(pending.data.requires_confirmation)
        self.assertEqual(pending.metadata["permission"], "confirm_required")
        self.assertEqual(pending.metadata["query"].status, TODO_COMPLETED)

        deleted = ability.execute({"text": "완료된 할 일 삭제해", "_confirmed": True})

        self.assertTrue(deleted.success)
        self.assertEqual(len(deleted.data.todos), 2)
        self.assertEqual(repository.find(active.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(completed_one.id).status, TODO_CANCELLED)
        self.assertEqual(repository.find(completed_two.id).status, TODO_CANCELLED)
        self.assertIn("외 1건", deleted.data.to_natural_language())

    def test_active_list_falls_back_to_completed_when_no_active_todos(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        todo = repository.create("우유 사기")
        repository.complete(todo.id)

        listed = ability.execute({"text": "할일 알려줘"})

        self.assertTrue(listed.success)
        self.assertEqual(len(listed.data.todos), 1)
        self.assertEqual(listed.data.todos[0].status, TODO_COMPLETED)
        self.assertIn("완료", listed.data.to_natural_language())

    def test_default_list_includes_active_and_completed_todos(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        active = repository.create("라면 사기")
        completed = repository.complete(repository.create("우유 사기").id)

        listed = ability.execute({"text": "할일 보여줘"})

        self.assertTrue(listed.success)
        self.assertEqual({todo.id for todo in listed.data.todos}, {active.id, completed.id})
        self.assertIn("완료", listed.data.to_natural_language())

    def test_second_ordinal_complete_targets_second_active_todo(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        first = repository.create("우유 사기")
        second = repository.create("라면 사기")

        result = ability.execute({"text": "할일 2번 완료했어", "_confirmed": True})

        self.assertTrue(result.success)
        self.assertEqual(repository.find(first.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(second.id).status, TODO_COMPLETED)

    def test_ai_complete_without_target_is_enriched_from_raw_text(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        first = repository.create("우유 사기")
        second = repository.create("라면 사기")

        result = ability.execute(
            {
                "action": "complete",
                "raw_text": "두번째거 완료했어",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(repository.find(first.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(second.id).status, TODO_COMPLETED)

    def test_complete_multiple_ordinal_todos(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        first = repository.create("우유 사기")
        second = repository.create("라면 사기")
        third = repository.create("고기 사기")

        result = ability.execute({"text": "할 일 1번, 3번 완료했어", "_confirmed": True})

        self.assertTrue(result.success)
        self.assertEqual(len(result.data.todos), 2)
        self.assertEqual(repository.find(first.id).status, TODO_COMPLETED)
        self.assertEqual(repository.find(second.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(third.id).status, TODO_COMPLETED)

    def test_ai_title_ordinal_is_treated_as_ordinal_reference(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        first = repository.create("우유 사기")
        second = repository.create("라면 사기")
        third = repository.create("고기 사기")

        result = ability.execute(
            {
                "action": "complete",
                "title": "3번",
                "raw_text": "3번 완료했어",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(repository.find(first.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(second.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(third.id).status, TODO_COMPLETED)

    def test_complete_multiple_title_references(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        first = repository.create("우유 사기")
        second = repository.create("라면 사기")
        third = repository.create("고기 사기")

        result = ability.execute({"text": "우유 사기랑 라면 사기 완료했어", "_confirmed": True})

        self.assertTrue(result.success)
        self.assertEqual(repository.find(first.id).status, TODO_COMPLETED)
        self.assertEqual(repository.find(second.id).status, TODO_COMPLETED)
        self.assertEqual(repository.find(third.id).status, TODO_ACTIVE)

    def test_ai_lowercase_completed_status_deletes_completed_todos(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        active = repository.create("고기 사기")
        completed = repository.complete(repository.create("우유 사기").id)

        result = ability.execute(
            {
                "action": "delete",
                "status": "completed",
                "raw_text": "완료된 할일 삭제해 줘",
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(repository.find(active.id).status, TODO_ACTIVE)
        self.assertEqual(repository.find(completed.id).status, TODO_CANCELLED)

    def test_delete_without_active_todo_does_not_ask_confirmation(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)

        result = ability.execute({"text": "\ud560 \uc77c \uc0ad\uc81c\ud574"})

        self.assertFalse(result.success)
        self.assertEqual(result.data.error_code, "todo_not_found")
        self.assertFalse(result.data.requires_confirmation)
        self.assertNotIn("permission", result.metadata)

    def test_not_found_failure_has_spoken_error(self):
        ability = TodoAbility(repository=TodoRepository())

        result = ability.execute({"text": "없는 할 일 삭제해", "_confirmed": True})

        self.assertFalse(result.success)
        self.assertIn("할 일", result.error)

    def test_parser_due_at_for_tomorrow_time(self):
        query = TodoIntentParser().parse("내일 오후 5시에 약 사기 추가해")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.title, "약 사기")
        self.assertRegex(query.due_at, r"^\d{4}-\d{2}-\d{2}T17:00:00$")

    def test_parser_due_at_for_tomorrow_spoken_time_word(self):
        query = TodoIntentParser().parse("내일 오후 다섯 시에 약 사기 추가해")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.title, "약 사기")
        self.assertRegex(query.due_at, r"^\d{4}-\d{2}-\d{2}T17:00:00$")

    def test_parser_treats_save_as_todo_create(self):
        query = TodoIntentParser().parse("봉투 사기 저장해")

        self.assertEqual(query.action, "create")
        self.assertEqual(query.title, "봉투 사기")

    def test_last_visible_list_controls_ordinal_references(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        todos = [repository.create(f"todo {index}") for index in range(1, 6)]
        repository.complete(todos[1].id)
        repository.complete(todos[2].id)

        all_list = ability.execute({"text": "할일 알려줘"})
        self.assertEqual([todo.id for todo in all_list.data.todos], [todo.id for todo in todos])
        self.assertEqual(
            [todo.status for todo in all_list.data.todos],
            [TODO_ACTIVE, TODO_COMPLETED, TODO_COMPLETED, TODO_ACTIVE, TODO_ACTIVE],
        )

        completed = ability.execute({"text": "2번 완료했어", "_confirmed": True})

        self.assertTrue(completed.success)
        self.assertEqual(repository.find(todos[1].id).status, TODO_COMPLETED)
        self.assertEqual(repository.find(todos[0].id).status, TODO_ACTIVE)

    def test_filtered_lists_set_ordinal_context_and_bulk_completed_delete(self):
        repository = TodoRepository()
        ability = TodoAbility(repository=repository)
        todos = [repository.create(f"todo {index}") for index in range(1, 6)]
        repository.complete(todos[1].id)
        repository.complete(todos[2].id)

        all_list = ability.execute({"text": "할일 알려줘"})
        self.assertEqual(
            [todo.status for todo in all_list.data.todos],
            [TODO_ACTIVE, TODO_COMPLETED, TODO_COMPLETED, TODO_ACTIVE, TODO_ACTIVE],
        )

        active_list = ability.execute({"text": "진행중 할일 보여줘"})
        self.assertEqual([todo.id for todo in active_list.data.todos], [todos[0].id, todos[3].id, todos[4].id])

        completed_list = ability.execute({"text": "완료된 할일 보여줘"})
        self.assertEqual([todo.id for todo in completed_list.data.todos], [todos[1].id, todos[2].id])

        deleted = ability.execute({"text": "완료된 할일 삭제해", "_confirmed": True})
        self.assertTrue(deleted.success)
        self.assertEqual([todo.id for todo in deleted.data.todos], [todos[1].id, todos[2].id])

        active_after_delete = ability.execute({"text": "진행중 할일 보여줘"})
        self.assertEqual([todo.id for todo in active_after_delete.data.todos], [todos[0].id, todos[3].id, todos[4].id])


if __name__ == "__main__":
    unittest.main()
