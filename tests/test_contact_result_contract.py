import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.contacts import ContactAbility
from jarvis.core.contacts import ContactRepository, InMemoryContactStorage
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry, ToolRequest


class TestContactResultContract(unittest.TestCase):
    """Check ContactResult is a structured contract, not just text."""

    def setUp(self):
        self.repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        ability_registry = AbilityRegistry()
        ability_registry.register(ContactAbility(repository=self.repository))
        tool_registry = ToolRegistry()
        ability_registry.register_tools(tool_registry)
        self.dispatcher = RuntimeToolDispatcher(tool_registry)

    def test_create_result_has_revision_event_and_no_message(self):
        pending = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야를 연락처에 저장해"}))
        confirmed = self.dispatcher.execute(
            ToolRequest("contacts", dict(pending.output.metadata["query"].to_input_data(), _confirmed=True))
        )
        result = confirmed.output.data

        self.assertTrue(result.success)
        self.assertEqual(result.action, "create")
        self.assertEqual(result.changed_fields, ("id", "display_name"))
        self.assertEqual(result.revision, 1)
        self.assertTrue(result.event_id.startswith("CE-"))
        self.assertEqual(result.trace_id, result.event_id)
        self.assertEqual(result.provider, "memory")
        self.assertGreaterEqual(result.execution_time_ms, 0)
        self.assertEqual(result.correlation_id, "")
        self.assertEqual(result.message, "")
        self.assertIn("저장했습니다", result.to_natural_language())

    def test_update_and_get_results_carry_contract_fields(self):
        pending = self.dispatcher.execute(ToolRequest("contacts", {"text": "유이 이메일은 test@test.com이야"}))
        confirmed = self.dispatcher.execute(
            ToolRequest("contacts", dict(pending.output.metadata["query"].to_input_data(), _confirmed=True))
        )
        update_result = confirmed.output.data

        self.assertEqual(update_result.action, "update")
        self.assertEqual(update_result.changed_fields, ("emails",))
        self.assertEqual(update_result.revision, 1)
        self.assertTrue(update_result.event_id.startswith("CE-"))
        self.assertEqual(update_result.provider, "memory")
        self.assertGreaterEqual(update_result.execution_time_ms, 0)
        self.assertEqual(update_result.message, "")

        recall = self.dispatcher.execute(ToolRequest("contacts", {"text": "유이 이메일 알려줘"}))
        recall_result = recall.output.data

        self.assertEqual(recall_result.action, "get")
        self.assertEqual(recall_result.changed_fields, ("email",))
        self.assertEqual(recall_result.revision, 1)
        self.assertEqual(recall_result.provider, "memory")
        self.assertGreaterEqual(recall_result.execution_time_ms, 0)
        self.assertIn("test@test.com", recall_result.to_natural_language())

    def test_correlation_id_flows_into_contact_result(self):
        pending = self.dispatcher.execute(
            ToolRequest("contacts", {"text": "아야를 연락처에 저장해", "correlation_id": "corr-123"})
        )
        pending_result = pending.output.data

        self.assertEqual(pending_result.correlation_id, "corr-123")
        self.assertEqual(pending_result.provider, "memory")

        confirmed_input = dict(pending.output.metadata["query"].to_input_data(), _confirmed=True, correlation_id="corr-123")
        confirmed = self.dispatcher.execute(ToolRequest("contacts", confirmed_input))

        self.assertEqual(confirmed.output.data.correlation_id, "corr-123")


if __name__ == "__main__":
    unittest.main()
