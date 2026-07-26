from dataclasses import replace
from hashlib import sha256
from json import dumps
from time import perf_counter

from jarvis.runtime.task.models import (
    ClarificationTurn,
    ConversationContext,
    PendingArtifact,
    PendingQuestion,
    RuntimeTask,
    TaskState,
    now_iso,
)


TERMINAL_TASK_STATES = {
    TaskState.COMPLETED,
    TaskState.SUCCESS,
    TaskState.FAILED,
    TaskState.CANCELLED,
    TaskState.PARTIAL_SUCCESS,
}


class ConversationResolver:
    """Own transient conversation updates on behalf of RuntimeTask."""

    def ensure_task(self, task=None, goal=""):
        return task or RuntimeTask(id="", goal=str(goal or "conversation"))

    def set_question(self, task, kind, payload=None, text="", turns=2, seconds=45.0):
        question = PendingQuestion(
            kind=str(kind or ""),
            text=str(text or ""),
            payload=dict(payload or {}),
            turns_remaining=max(0, int(turns)),
            expires_at=perf_counter() + float(seconds),
        )
        return self.update_context(
            task,
            pending_question=question,
            pending_answer="",
            expires_at=question.expires_at,
        )

    def get_question(self, task):
        context = task.conversation_context
        question = context.pending_question if context is not None else None
        if question is None:
            return None
        if question.turns_remaining <= 0 or perf_counter() > question.expires_at:
            return None
        return question

    def advance_question(self, task):
        question = self.get_question(task)
        if question is None or question.turns_remaining <= 1:
            return self.clear_question(task)
        return self.update_context(
            task,
            pending_question=replace(question, turns_remaining=question.turns_remaining - 1),
        )

    def answer_question(self, task, answer_kind):
        question = self.get_question(task)
        if question is None:
            return task
        history = task.conversation_context.clarification_history + (
            ClarificationTurn(
                question_kind=question.kind,
                answer_kind=str(answer_kind or ""),
                occurred_at=now_iso(),
            ),
        )
        return self.update_context(
            task,
            pending_question=None,
            pending_answer=str(answer_kind or ""),
            clarification_history=history,
            expires_at=0.0,
        )

    def clear_question(self, task):
        return self.update_context(
            task,
            pending_question=None,
            pending_answer="",
            expires_at=0.0,
        )

    def select(self, task, key, value):
        selected = dict(task.conversation_context.selected_entities)
        selected[str(key)] = value
        return self.update_context(task, selected_entities=selected)

    def selected(self, task, key, default=None):
        return task.conversation_context.selected_entities.get(str(key), default)

    def add_artifact(self, task, artifact_type, artifact_id, payload, verified=False):
        artifact = PendingArtifact(
            artifact_type=str(artifact_type or ""),
            artifact_id=str(artifact_id or ""),
            fingerprint=artifact_fingerprint(payload),
            created_at=now_iso(),
            verified=bool(verified),
            payload=payload,
        )
        artifacts = tuple(
            item
            for item in task.conversation_context.pending_artifacts
            if item.artifact_id != artifact.artifact_id
        ) + (artifact,)
        return self.update_context(task, pending_artifacts=artifacts)

    def artifact(self, task, artifact_type):
        return next(
            (
                item
                for item in reversed(task.conversation_context.pending_artifacts)
                if item.artifact_type == str(artifact_type or "")
            ),
            None,
        )

    def set_confirmation(self, task, state):
        return self.update_context(task, confirmation_state=str(state or ""))

    def cleanup(self, task):
        return replace(
            task,
            conversation_context=ConversationContext(
                task_id=task.id,
                goal=task.goal,
                current_step=task.current_step,
            ),
        )

    def cleanup_if_terminal(self, task):
        return self.cleanup(task) if task.status in TERMINAL_TASK_STATES else task

    def update_context(self, task, **changes):
        context = replace(
            task.conversation_context,
            task_id=task.id,
            goal=task.goal,
            current_step=task.current_step,
            **changes,
        )
        return replace(task, conversation_context=context)


def artifact_fingerprint(payload):
    """Hash an artifact without persisting its sensitive body in diagnostics."""
    try:
        encoded = dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        encoded = repr(payload)
    return sha256(encoded.encode("utf-8")).hexdigest()
