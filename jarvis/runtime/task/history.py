from collections import deque


class TaskHistory:
    """In-memory history of completed runtime tasks."""

    def __init__(self, limit=100):
        """Create a bounded task history."""
        self.limit = int(limit)
        self._items = deque(maxlen=self.limit)

    def add(self, task):
        """Store one task snapshot."""
        self._items.append(task)
        return task

    def list(self):
        """Return task snapshots from oldest to newest."""
        return list(self._items)

    def latest(self):
        """Return the latest task snapshot."""
        if len(self._items) == 0:
            return None

        return self._items[-1]
