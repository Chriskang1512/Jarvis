from copy import deepcopy
from types import MappingProxyType


CONTEXT_VERSION = "1.0"


class ExecutionContext:
    """Temporary execution-only context owned by the Runner."""

    def __init__(self, execution_id):
        """Create an empty execution context."""
        self.execution_id = execution_id
        self.values = {}
        self.destroyed = False

    def store_result(self, node_id, result):
        """Store one node result for later sequential nodes."""
        self.values[node_id] = {
            "result": result,
        }

    def snapshot(self):
        """Return the current context contract."""
        return freeze_mapping(
            {
                "context_version": CONTEXT_VERSION,
                "execution_id": self.execution_id,
                "values": deepcopy(self.values),
            }
        )

    def destroy(self):
        """Destroy temporary context after execution."""
        self.values.clear()
        self.destroyed = True


def freeze_mapping(value):
    """Return a recursively read-only mapping/list view."""
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: freeze_mapping(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, list):
        return tuple(freeze_mapping(item) for item in value)

    return value
