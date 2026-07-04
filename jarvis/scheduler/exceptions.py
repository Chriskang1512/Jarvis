class SchedulerError(Exception):
    """Base scheduler exception."""


class SchedulerTaskNotFound(SchedulerError):
    """Raised when a scheduled task cannot be found."""
