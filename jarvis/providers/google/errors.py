"""Google provider errors mapped to Jarvis contracts."""


AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_EXPIRED = "AUTH_EXPIRED"
AUTH_REFRESH_FAILED = "AUTH_REFRESH_FAILED"
SCOPE_INSUFFICIENT = "SCOPE_INSUFFICIENT"
PERMISSION_DENIED = "PERMISSION_DENIED"
PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
INVALID_PROVIDER_RESPONSE = "INVALID_PROVIDER_RESPONSE"
FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"


class GoogleProviderError(Exception):
    """Provider failure with a safe public error code."""

    def __init__(self, code, message="", *, cause=None):
        """Create an error with a stable code and safe message."""
        super().__init__(message or code)
        self.code = str(code or PROVIDER_UNAVAILABLE)
        self.safe_message = str(message or google_error_message(self.code))
        self.cause = cause


def google_error_message(code):
    """Return a user-safe Korean message for a Google provider error code."""
    messages = {
        AUTH_REQUIRED: "Google Calendar 인증이 필요합니다.",
        AUTH_EXPIRED: "Google Calendar 인증이 만료되었습니다.",
        AUTH_REFRESH_FAILED: "Google Calendar 인증을 갱신하지 못했습니다.",
        SCOPE_INSUFFICIENT: "Google Calendar 읽기 권한이 없습니다.",
        PERMISSION_DENIED: "Google Calendar 접근 권한이 없습니다.",
        PROVIDER_TIMEOUT: "Google Calendar 응답이 지연되고 있습니다.",
        RATE_LIMITED: "Google Calendar 요청 한도를 초과했습니다.",
        PROVIDER_UNAVAILABLE: "Google Calendar 서비스를 현재 사용할 수 없습니다.",
        INVALID_PROVIDER_RESPONSE: "Google Calendar 응답을 이해하지 못했습니다.",
        FEATURE_NOT_ENABLED: "이 Google Calendar 기능은 아직 활성화되지 않았습니다.",
    }
    return messages.get(str(code or ""), "Google Calendar 요청을 처리하지 못했습니다.")


def map_google_exception(error):
    """Map arbitrary Google/client exceptions to a safe provider error."""
    status = getattr(getattr(error, "resp", None), "status", None)
    text = str(error or "").lower()

    if status in {401}:
        return GoogleProviderError(AUTH_REQUIRED)
    if status in {403}:
        return GoogleProviderError(PERMISSION_DENIED)
    if status in {408, 504} or "timeout" in text:
        return GoogleProviderError(PROVIDER_TIMEOUT)
    if status == 429 or "rate" in text:
        return GoogleProviderError(RATE_LIMITED)
    if status and int(status) >= 500:
        return GoogleProviderError(PROVIDER_UNAVAILABLE)

    return GoogleProviderError(PROVIDER_UNAVAILABLE)
