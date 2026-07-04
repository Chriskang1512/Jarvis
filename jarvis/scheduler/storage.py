from typing import Protocol


class TaskStore(Protocol):
    """Storage contract for scheduled tasks."""

    def save(self, task):
        """Save one task."""
        ...

    def get(self, task_id):
        """Return one task by ID or None."""
        ...

    def list(self):
        """Return all stored tasks."""
        ...


class InMemoryTaskStore:
    """In-memory task store for Scheduler Foundation."""

    def __init__(self):
        """Create an empty store."""
        self.tasks = {}

    def save(self, task):
        """Save one task and return it."""
        self.tasks[task.task_id] = task
        return task

    def get(self, task_id):
        """Return one task by ID or None."""
        return self.tasks.get(task_id)

    def list(self):
        """Return all tasks in insertion order."""
        return list(self.tasks.values())
