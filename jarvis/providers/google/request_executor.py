"""Google request executor component."""

from dataclasses import dataclass
from time import perf_counter

from jarvis.providers.google.error_mapper import GoogleErrorMapper
from jarvis.providers.google.errors import GoogleProviderError


@dataclass(frozen=True)
class GoogleRequestResult:
    """Result of one Google request execution."""

    success: bool
    response: object = None
    error: GoogleProviderError | None = None
    execution_time_ms: int = 0


class GoogleRequestExecutor:
    """Execute Google API requests with consistent timing and error mapping."""

    def __init__(self, error_mapper=None):
        """Create executor."""
        self.error_mapper = error_mapper or GoogleErrorMapper()

    def execute(self, request_factory):
        """Execute a request factory and return a structured result."""
        started = perf_counter()

        try:
            request = request_factory()
            response = request.execute() if hasattr(request, "execute") else request
            return GoogleRequestResult(True, response=response, execution_time_ms=elapsed_ms(started))
        except GoogleProviderError as error:
            return GoogleRequestResult(False, error=error, execution_time_ms=elapsed_ms(started))
        except Exception as error:
            return GoogleRequestResult(
                False,
                error=self.error_mapper.map_exception(error),
                execution_time_ms=elapsed_ms(started),
            )


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)
