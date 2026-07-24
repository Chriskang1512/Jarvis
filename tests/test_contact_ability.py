import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.contacts import ContactAbility
from jarvis.core.contacts import ContactRepository, InMemoryContactStorage
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry, ToolRequest


class TestContactAbilityVerticalSlice(unittest.TestCase):
    """Test Contact Ability from planner/dispatcher down to repository."""

    def setUp(self):
        self.repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        ability_registry = AbilityRegistry()
        ability_registry.register(ContactAbility(repository=self.repository))
        self.tool_registry = ToolRegistry()
        ability_registry.register_tools(self.tool_registry)
        self.dispatcher = RuntimeToolDispatcher(self.tool_registry)

    def test_create_requires_confirmation_then_creates_contact(self):
        result = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야를 연락처에 저장해"}))
        ability_result = result.output

        self.assertTrue(result.success)
        self.assertEqual(ability_result.metadata["permission"], "confirm_required")
        self.assertIn("저장할까요", ability_result.to_natural_language())
        self.assertIsNone(self.repository.resolve("아야"))

        confirmed = self.dispatcher.execute(
            ToolRequest("contacts", dict(ability_result.metadata["query"].to_input_data(), _confirmed=True))
        )

        self.assertTrue(confirmed.success)
        self.assertEqual(self.repository.resolve("아야").id, "person_aya")
        self.assertIn("저장했습니다", confirmed.output.to_natural_language())
        self.assertEqual(self.repository.events[-1].event_type, "ContactCreated")

    def test_update_and_get_birthday(self):
        create_result = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야를 연락처에 저장해"}))
        self.dispatcher.execute(ToolRequest("contacts", dict(create_result.output.metadata["query"].to_input_data(), _confirmed=True)))

        update_result = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야 생일은 2월 28일이야"}))
        self.assertEqual(update_result.output.metadata["permission"], "confirm_required")
        self.dispatcher.execute(ToolRequest("contacts", dict(update_result.output.metadata["query"].to_input_data(), _confirmed=True)))

        recall = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야 생일 언제야"}))

        self.assertTrue(recall.success)
        self.assertIn("2월 28일", recall.output.to_natural_language())
        self.assertEqual(self.repository.resolve("아야").birthday, "02-28")
        self.assertEqual(self.repository.resolve("아야").revision, 2)

    def test_email_alias_lookup_and_delete(self):
        update_result = self.dispatcher.execute(ToolRequest("contacts", {"text": "유이 이메일은 test@test.com이야"}))
        self.dispatcher.execute(ToolRequest("contacts", dict(update_result.output.metadata["query"].to_input_data(), _confirmed=True)))

        recall = self.dispatcher.execute(ToolRequest("contacts", {"text": "유이 이메일 알려줘"}))
        self.assertIn("test@test.com", recall.output.to_natural_language())

        aya_create = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야를 연락처에 저장해"}))
        self.dispatcher.execute(ToolRequest("contacts", dict(aya_create.output.metadata["query"].to_input_data(), _confirmed=True)))
        birthday = self.dispatcher.execute(ToolRequest("contacts", {"text": "Aya 생일 언제야"}))
        self.assertIn("아직 저장", birthday.output.to_natural_language())

        delete_result = self.dispatcher.execute(ToolRequest("contacts", {"text": "아야 연락처 삭제해"}))
        self.assertEqual(delete_result.output.metadata["permission"], "confirm_required")
        self.dispatcher.execute(ToolRequest("contacts", dict(delete_result.output.metadata["query"].to_input_data(), _confirmed=True)))
        self.assertIsNone(self.repository.resolve("아야"))
        self.assertEqual(self.repository.events[-1].event_type, "ContactDeleted")

    def test_planner_routes_contact_queries_to_contacts(self):
        plan = self.dispatcher.create_plan("아야 생일 언제야")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "contacts")
        self.assertEqual(plan.steps[0].action, "get")

    def test_planner_routes_contact_phone_search_as_get(self):
        plan = self.dispatcher.create_plan("아야 전화번호 찾아줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "contacts")
        self.assertEqual(plan.steps[0].action, "get")

    def test_planner_routes_contact_phone_change_as_update(self):
        plan = self.dispatcher.create_plan("차희 전화번호를 010-1234-5678로 바꿔줘")

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "contacts")
        self.assertEqual(plan.steps[0].action, "update")


if __name__ == "__main__":
    unittest.main()
