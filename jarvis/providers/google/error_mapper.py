"""Google error mapper component."""

from jarvis.providers.google.errors import google_error_message, map_google_exception


class GoogleErrorMapper:
    """Map provider exceptions and codes into Jarvis-safe errors."""

    def map_exception(self, error):
        """Return a GoogleProviderError for an arbitrary exception."""
        return map_google_exception(error)

    def message_for_code(self, code):
        """Return a safe user-facing message."""
        return google_error_message(code)
