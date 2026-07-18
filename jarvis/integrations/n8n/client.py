import json
import urllib.error
import urllib.request

from jarvis.integrations.bridge.errors import AUTH_FAILED, INVALID_RESPONSE, NETWORK_ERROR, TIMEOUT


class N8nHttpClient:
    """Tiny HTTP client for n8n webhook execution."""

    def __init__(self, config):
        """Create client with loaded n8n config."""
        self.config = config

    def post_workflow(self, url, payload, timeout_seconds, headers=None):
        """POST JSON payload to one n8n workflow URL."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers=dict(headers or {}, **{"Content-Type": "application/json"}),
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
                return response.status, json.loads(raw_body)
        except TimeoutError as error:
            raise IntegrationTransportError(TIMEOUT, str(error)) from error
        except urllib.error.HTTPError as error:
            if error.code in [401, 403]:
                raise IntegrationTransportError(AUTH_FAILED, f"HTTP {error.code}") from error

            raise IntegrationTransportError(NETWORK_ERROR, f"HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise IntegrationTransportError(NETWORK_ERROR, str(error.reason)) from error
        except json.JSONDecodeError as error:
            raise IntegrationTransportError(INVALID_RESPONSE, str(error)) from error


class IntegrationTransportError(Exception):
    """Transport-layer integration error."""

    def __init__(self, code, message):
        """Create transport error."""
        super().__init__(message)
        self.code = code
        self.message = message
