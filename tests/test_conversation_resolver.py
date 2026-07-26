import unittest

from jarvis.runtime.conversation_resolver import ConversationResolver
from jarvis.runtime.task import RuntimeTask, TaskState, TaskStateMachine


class TestConversationResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = ConversationResolver()
        self.task = RuntimeTask(id="RT-CONVERSATION", goal="mail follow-up")

    def test_question_and_artifact_belong_to_runtime_task(self):
        task = self.resolver.set_question(
            self.task,
            "contact_ambiguous",
            payload={"candidate_ids": ["1", "2"]},
            text="which contact",
        )
        task = self.resolver.add_artifact(task, "mail_draft", "draft-1", {"body": "secret"})
        self.assertEqual(task.conversation_context.task_id, task.id)
        self.assertEqual(self.resolver.get_question(task).kind, "contact_ambiguous")
        self.assertEqual(self.resolver.artifact(task, "mail_draft").artifact_id, "draft-1")
        self.assertNotIn("secret", str(task.to_dict()["conversation_context"]))

    def test_answer_records_privacy_safe_clarification_history(self):
        task = self.resolver.set_question(self.task, "contact_ambiguous")
        task = self.resolver.answer_question(task, "ordinal")
        self.assertIsNone(task.conversation_context.pending_question)
        self.assertEqual(task.conversation_context.clarification_history[0].question_kind, "contact_ambiguous")
        self.assertEqual(task.conversation_context.clarification_history[0].answer_kind, "ordinal")

    def test_terminal_transition_cleans_transient_context(self):
        task = self.resolver.select(self.task, "mail_selected_message", object())
        task = self.resolver.add_artifact(task, "mail_draft", "draft-1", {"body": "secret"})
        machine = TaskStateMachine()
        task = machine.transition(task, TaskState.PLANNING)
        task = machine.transition(task, TaskState.VALIDATING)
        task = machine.transition(task, TaskState.OPTIMIZING)
        task = machine.transition(task, TaskState.READY)
        task = machine.transition(task, TaskState.CANCELLED, reason="user_cancelled")
        self.assertEqual(task.conversation_context.selected_entities, {})
        self.assertEqual(task.conversation_context.pending_artifacts, ())


if __name__ == "__main__":
    unittest.main()
