import unittest

from jarvis.abilities.native.todo.result import TodoResult
from jarvis.abilities.result import BaseAbilityResult


class TodoResultContractTest(unittest.TestCase):
    def test_todo_result_extends_base_ability_result(self):
        result = TodoResult(
            success=True,
            action="create",
            revision=2,
            event_id="E-1",
            trace_id="T-1",
            correlation_id="C-1",
            provider="memory",
            execution_time_ms=12,
            changed_fields=("title",),
        )

        self.assertIsInstance(result, BaseAbilityResult)
        self.assertEqual(result.provider, "memory")
        self.assertEqual(result.execution_time_ms, 12)
        self.assertEqual(result.correlation_id, "C-1")
        self.assertEqual(result.changed_fields, ("title",))


if __name__ == "__main__":
    unittest.main()
