class AgentRuntimeError(Exception):
    """Base Agent Runtime exception."""


class AgentRuntimeStopped(AgentRuntimeError):
    """Raised when a stopped runtime is asked to tick."""
