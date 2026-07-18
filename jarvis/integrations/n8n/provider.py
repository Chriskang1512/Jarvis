from time import perf_counter
from urllib.parse import urljoin, urlparse

from jarvis.debug_trace import trace_event
from jarvis.integrations.bridge import IntegrationHealth, IntegrationMetrics, IntegrationProviderCapabilities, IntegrationResult
from jarvis.integrations.bridge.errors import (
    INTEGRATION_DISABLED,
    INVALID_RESPONSE,
    REMOTE_EXECUTION_FAILED,
    WORKFLOW_NOT_FOUND,
)
from jarvis.integrations.n8n.client import IntegrationTransportError, N8nHttpClient
from jarvis.integrations.n8n.config import load_n8n_config
from jarvis.integrations.n8n.registry import WorkflowRegistry


PROVIDER_METRICS = {}


class MockIntegrationBridge:
    """Offline integration bridge for tests and local development."""

    provider_name = "mock"

    def __init__(self, registry=None):
        """Create mock bridge."""
        self.registry = registry or WorkflowRegistry()
        self.capabilities = IntegrationProviderCapabilities(
            health=True,
            execute=True,
            supports_confirmation=True,
            supports_stream=False,
            supports_async=False,
        )
        self.metrics = get_provider_metrics(self.provider_name)

    def health(self):
        """Return healthy mock bridge status."""
        return IntegrationHealth(provider=self.provider_name, enabled=True, reachable=True, authenticated=True)

    def execute(self, request):
        """Execute a known mock workflow."""
        started = perf_counter()
        trace_event("integration.provider", requested="mock", used="mock", workflow=request.workflow_key)

        if not self.registry.exists(request.workflow_key):
            return integration_error(request, WORKFLOW_NOT_FOUND, "등록되지 않은 workflow입니다.", self.provider_name, started)

        if request.workflow_key == "system.health":
            data = {"ok": True, "provider": self.provider_name}
            return integration_success(request, data, "n8n Bridge 상태는 정상입니다.", self.provider_name, started)

        if request.workflow_key == "system.echo":
            message = str(request.payload.get("message") or request.payload.get("text") or "")
            data = {"echo": message}
            return integration_success(request, data, message or "echo", self.provider_name, started)

        if request.workflow_key == "notification.test":
            message = str(request.payload.get("message") or "테스트 알림을 보냈습니다.")
            data = {"sent": True, "message": message}
            return integration_success(request, data, "테스트 알림을 실행했습니다.", self.provider_name, started)

        return integration_error(request, WORKFLOW_NOT_FOUND, "등록되지 않은 workflow입니다.", self.provider_name, started)


class N8nBridgeProvider:
    """n8n webhook integration bridge."""

    provider_name = "n8n"

    def __init__(self, config=None, registry=None, client=None):
        """Create n8n bridge provider."""
        self.config = config or load_n8n_config()
        self.registry = registry or WorkflowRegistry()
        self.client = client or N8nHttpClient(self.config)
        self.capabilities = IntegrationProviderCapabilities(
            health=True,
            execute=True,
            supports_confirmation=True,
            supports_stream=False,
            supports_async=False,
        )
        self.metrics = get_provider_metrics(self.provider_name)

    def health(self):
        """Return config-level health without calling n8n by default."""
        enabled = bool(self.config.bridge_enabled)
        has_url = self.is_valid_base_url()
        authenticated = bool(self.config.api_token or self.config.webhook_secret)
        error = ""

        if not enabled:
            error = INTEGRATION_DISABLED
        elif not has_url:
            error = "INVALID_BASE_URL"

        return IntegrationHealth(
            provider=self.provider_name,
            enabled=enabled,
            reachable=enabled and has_url,
            authenticated=authenticated,
            error=error,
        )

    def execute(self, request):
        """Execute one registered n8n workflow."""
        started = perf_counter()
        trace_event("integration.provider", requested="n8n", used="n8n", workflow=request.workflow_key)

        if not self.config.bridge_enabled:
            return integration_error(request, INTEGRATION_DISABLED, "n8n Bridge가 비활성화되어 있습니다.", self.provider_name, started)

        workflow = self.registry.get(request.workflow_key)

        if workflow is None or not workflow.enabled:
            return integration_error(request, WORKFLOW_NOT_FOUND, "등록되지 않은 workflow입니다.", self.provider_name, started)

        if not self.is_valid_base_url():
            return integration_error(request, INTEGRATION_DISABLED, "n8n Base URL이 올바르지 않습니다.", self.provider_name, started)

        try:
            status, response = self.client.post_workflow(
                urljoin(self.config.base_url.rstrip("/") + "/", workflow.webhook_path.lstrip("/")),
                payload=create_http_payload(request),
                timeout_seconds=request.timeout_seconds or workflow.timeout_seconds,
                headers=self.create_headers(request),
            )
        except IntegrationTransportError as error:
            return integration_error(request, error.code, error.message, self.provider_name, started, retryable=True)

        result = validate_remote_response(request, response, self.provider_name, started, status)
        trace_event("integration.response", status=status, duration_ms=result.duration_ms, workflow=request.workflow_key)
        if result.success:
            trace_event("integration.completed", workflow=request.workflow_key, success=True, duration_ms=result.duration_ms)
        return result

    def is_valid_base_url(self):
        """Return whether base_url is an HTTPS URL."""
        parsed = urlparse(str(self.config.base_url or ""))
        return parsed.scheme == "https" and parsed.netloc != ""

    def create_headers(self, request):
        """Create auth headers without logging secrets."""
        headers = {"X-Jarvis-Request-Id": request.request_id, "X-Idempotency-Key": request.idempotency_key}

        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"

        if self.config.webhook_secret:
            headers["X-Jarvis-Webhook-Secret"] = self.config.webhook_secret

        return headers


def create_integration_bridge(config=None, registry=None):
    """Create integration bridge from provider config."""
    config = config or load_n8n_config()

    if config.provider == "n8n":
        return N8nBridgeProvider(config=config, registry=registry)

    return MockIntegrationBridge(registry=registry)


def create_http_payload(request):
    """Create sanitized n8n request payload."""
    return {
        "request_id": request.request_id,
        "conversation_id": request.conversation_id,
        "session_id": request.session_id,
        "workflow_id": request.workflow_id,
        "workflow_key": request.workflow_key,
        "action": request.action,
        "payload": request.payload,
        "idempotency_key": request.idempotency_key,
        "retry": {
            "max_retry": request.max_retry,
            "retry_delay_seconds": request.retry_delay_seconds,
        },
        "metadata": request.metadata,
    }


def validate_remote_response(request, response, provider, started, status):
    """Validate the minimal n8n response contract."""
    if not isinstance(response, dict):
        return integration_error(request, INVALID_RESPONSE, "n8n 응답이 JSON 객체가 아닙니다.", provider, started, status=status)

    if "success" not in response:
        return integration_error(request, INVALID_RESPONSE, "n8n 응답에 success가 없습니다.", provider, started, status=status)

    if response.get("request_id", request.request_id) != request.request_id:
        return integration_error(request, INVALID_RESPONSE, "n8n request_id가 일치하지 않습니다.", provider, started, status=status)

    if response.get("action", request.action) != request.action:
        return integration_error(request, INVALID_RESPONSE, "n8n action이 일치하지 않습니다.", provider, started, status=status)

    if not response.get("success"):
        return integration_error(
            request,
            REMOTE_EXECUTION_FAILED,
            str(response.get("error_message") or "원격 workflow 실행에 실패했습니다."),
            provider,
            started,
            status=status,
            data=dict(response.get("data", {}) or {}),
        )

    trace_event("integration.validation", success=True, workflow=request.workflow_key)
    result = IntegrationResult(
        success=True,
        request_id=request.request_id,
        workflow_key=request.workflow_key,
        action=request.action,
        conversation_id=request.conversation_id,
        session_id=request.session_id,
        workflow_id=request.workflow_id,
        status=str(status),
        data=dict(response.get("data", {}) or {}),
        message=str(response.get("message") or "실행했습니다."),
        provider=provider,
        duration_ms=elapsed_ms(started),
        raw_response_metadata={"http_status": status},
    )
    record_provider_metrics(provider, result)
    return result


def integration_success(request, data, message, provider, started):
    """Create a successful IntegrationResult."""
    result = IntegrationResult(
        success=True,
        request_id=request.request_id,
        workflow_key=request.workflow_key,
        action=request.action,
        conversation_id=request.conversation_id,
        session_id=request.session_id,
        workflow_id=request.workflow_id,
        status="ok",
        data=dict(data or {}),
        message=str(message or "실행했습니다."),
        provider=provider,
        duration_ms=elapsed_ms(started),
    )
    record_provider_metrics(provider, result)
    trace_event(
        "integration.completed",
        workflow=request.workflow_key,
        success=True,
        duration_ms=result.duration_ms,
        conversation_id=request.conversation_id,
        session_id=request.session_id,
        request_id=request.request_id,
        workflow_id=request.workflow_id,
    )
    return result


def integration_error(request, code, message, provider, started, retryable=False, status="", data=None):
    """Create a failed IntegrationResult."""
    result = IntegrationResult(
        success=False,
        request_id=request.request_id,
        workflow_key=request.workflow_key,
        action=request.action,
        conversation_id=request.conversation_id,
        session_id=request.session_id,
        workflow_id=request.workflow_id,
        status=str(status or "error"),
        data=dict(data or {}),
        provider=provider,
        duration_ms=elapsed_ms(started),
        retryable=retryable,
        error_code=code,
        error_message=message,
    )
    record_provider_metrics(provider, result)
    trace_event(
        "integration.failed",
        workflow=request.workflow_key,
        error_code=code,
        duration_ms=result.duration_ms,
        conversation_id=request.conversation_id,
        session_id=request.session_id,
        request_id=request.request_id,
        workflow_id=request.workflow_id,
    )
    return result


def get_provider_metrics(provider):
    """Return shared metrics for one provider name."""
    provider_name = str(provider or "unknown")

    if provider_name not in PROVIDER_METRICS:
        PROVIDER_METRICS[provider_name] = IntegrationMetrics()

    return PROVIDER_METRICS[provider_name]


def record_provider_metrics(provider, result):
    """Record metrics and emit a compact trace line."""
    metrics = get_provider_metrics(provider)
    metrics.record(result)
    trace_event("integration.metrics", provider=provider, **metrics.to_dict())


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)


_LegacyMockIntegrationBridge = MockIntegrationBridge
_LegacyN8nBridgeProvider = N8nBridgeProvider


class MockIntegrationBridge(_LegacyMockIntegrationBridge):
    """Offline integration bridge with clean Korean messages."""

    def execute(self, request):
        """Execute a known mock workflow."""
        started = perf_counter()
        trace_event("integration.provider", requested="mock", used="mock", workflow=request.workflow_key)

        if not self.registry.exists(request.workflow_key):
            return integration_error(request, WORKFLOW_NOT_FOUND, "등록되지 않은 workflow입니다.", self.provider_name, started)

        if request.workflow_key == "system.health":
            data = {"ok": True, "provider": self.provider_name}
            return integration_success(request, data, "n8n Bridge 상태는 정상입니다.", self.provider_name, started)

        if request.workflow_key == "system.echo":
            message = str(request.payload.get("message") or request.payload.get("text") or "")
            data = {"echo": message}
            return integration_success(request, data, message or "echo", self.provider_name, started)

        if request.workflow_key == "notification.test":
            message = str(request.payload.get("message") or "테스트 알림을 보냈습니다.")
            data = {"sent": True, "message": message}
            return integration_success(request, data, "테스트 알림을 실행했습니다.", self.provider_name, started)

        return integration_error(request, WORKFLOW_NOT_FOUND, "등록되지 않은 workflow입니다.", self.provider_name, started)


class N8nBridgeProvider(_LegacyN8nBridgeProvider):
    """n8n webhook integration bridge with clean Korean messages."""

    def execute(self, request):
        """Execute one registered n8n workflow."""
        started = perf_counter()
        trace_event("integration.provider", requested="n8n", used="n8n", workflow=request.workflow_key)

        if not self.config.bridge_enabled:
            return integration_error(request, INTEGRATION_DISABLED, "n8n Bridge가 비활성화되어 있습니다.", self.provider_name, started)

        workflow = self.registry.get(request.workflow_key)

        if workflow is None or not workflow.enabled:
            return integration_error(request, WORKFLOW_NOT_FOUND, "등록되지 않은 workflow입니다.", self.provider_name, started)

        if not self.is_valid_base_url():
            return integration_error(request, INTEGRATION_DISABLED, "n8n Base URL이 올바르지 않습니다.", self.provider_name, started)

        try:
            status, response = self.client.post_workflow(
                urljoin(self.config.base_url.rstrip("/") + "/", workflow.webhook_path.lstrip("/")),
                payload=create_http_payload(request),
                timeout_seconds=request.timeout_seconds or workflow.timeout_seconds,
                headers=self.create_headers(request),
            )
        except IntegrationTransportError as error:
            return integration_error(request, error.code, error.message, self.provider_name, started, retryable=True)

        result = validate_remote_response(request, response, self.provider_name, started, status)
        trace_event("integration.response", status=status, duration_ms=result.duration_ms, workflow=request.workflow_key)
        if result.success:
            trace_event("integration.completed", workflow=request.workflow_key, success=True, duration_ms=result.duration_ms)
        return result


def validate_remote_response(request, response, provider, started, status):
    """Validate the minimal n8n response contract."""
    if not isinstance(response, dict):
        return integration_error(request, INVALID_RESPONSE, "n8n 응답이 JSON 객체가 아닙니다.", provider, started, status=status)

    if "success" not in response:
        return integration_error(request, INVALID_RESPONSE, "n8n 응답에 success가 없습니다.", provider, started, status=status)

    if response.get("request_id", request.request_id) != request.request_id:
        return integration_error(request, INVALID_RESPONSE, "n8n request_id가 일치하지 않습니다.", provider, started, status=status)

    if response.get("action", request.action) != request.action:
        return integration_error(request, INVALID_RESPONSE, "n8n action이 일치하지 않습니다.", provider, started, status=status)

    if not response.get("success"):
        return integration_error(
            request,
            REMOTE_EXECUTION_FAILED,
            str(response.get("error_message") or "원격 workflow 실행에 실패했습니다."),
            provider,
            started,
            status=status,
            data=dict(response.get("data", {}) or {}),
        )

    trace_event("integration.validation", success=True, workflow=request.workflow_key)
    result = IntegrationResult(
        success=True,
        request_id=request.request_id,
        workflow_key=request.workflow_key,
        action=request.action,
        conversation_id=request.conversation_id,
        session_id=request.session_id,
        workflow_id=request.workflow_id,
        status=str(status),
        data=dict(response.get("data", {}) or {}),
        message=str(response.get("message") or "실행했습니다."),
        provider=provider,
        duration_ms=elapsed_ms(started),
        raw_response_metadata={"http_status": status},
    )
    record_provider_metrics(provider, result)
    return result
