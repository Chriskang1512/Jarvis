import unittest

from jarvis.abilities.native.todo.formatter import format_todo_result
from jarvis.abilities.native.todo.result import TodoResult
from jarvis.core.todos import TodoRepository


class TodoFormatterTest(unittest.TestCase):
    def test_create_and_list_messages(self):
        repository = TodoRepository()
        todo = repository.create("우유 사기")

        create_message = format_todo_result(TodoResult(success=True, action="create", todo=todo))
        self.assertEqual(create_message, "우유 사기 할 일을 추가했습니다.")

        list_message = format_todo_result(TodoResult(success=True, action="list", todos=(todo,)))
        self.assertIn("할 일은 1건입니다.", list_message)
        self.assertIn("우유 사기", list_message)

    def test_empty_and_missing_messages(self):
        self.assertEqual(format_todo_result(TodoResult(success=True, action="list")), "할 일이 없습니다.")
        self.assertEqual(
            format_todo_result(TodoResult(success=False, action="complete", error_code="todo_not_found")),
            "해당 할 일을 찾지 못했습니다.",
        )


if __name__ == "__main__":
    unittest.main()
