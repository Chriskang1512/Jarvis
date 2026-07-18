import unittest

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.integration.n8n import N8nIntegrationAbility
from jarvis.abilities.result import AbilityResult
from jarvis.integrations.bridge import IntegrationRequest
from jarvis.integrations.bridge.errors import INTEGRATION_DISABLED, INVALID_RESPONSE, TIMEOUT, WORKFLOW_NOT_FOUND
from jarvis.integrations.n8n.config import N8nConfig
from jarvis.integrations.n8n.client import IntegrationTransportError
from jarvis.integrations.n8n.provider import MockIntegrationBridge, N8nBridgeProvider, create_http_payload
from jarvis.integrations.n8n.registry import WorkflowRegistry
from jarvis.permissions import PermissionLevel
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolRegistry, ToolRequest


class TestIntegrationBridgeSprint7(unittest.TestCase):
    """Check Sprint 7 n8n Integration Bridge foundation."""

    def test_mock_system_echo_success(self):
        """Mock bridge executes system.echo without network."""
        request = IntegrationRequest(
            workflow_key="system.echo",
            action="system.echo",
            payload={"message": "hello"},
        )
        result = MockIntegrationBridge().execute(request)

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(result.data["echo"], "hello")
        self.assertEqual(result.message, "hello")

    def test_unknown_workflow_is_blocked_by_registry(self):
        """Unknown workflows fail closed."""
        request = IntegrationRequest(workflow_key="gmail.send", action="gmail.send")
        result = MockIntegrationBridge().execute(request)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, WORKFLOW_NOT_FOUND)

    def test_n8n_provider_disabled_fails_closed(self):
        """n8n provider does not execute when disabled."""
        provider = N8nBridgeProvider(config=N8nConfig(provider="n8n", bridge_enabled=False))
        request = IntegrationRequest(workflow_key="system.echo", action="system.echo")
        result = provider.execute(request)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, INTEGRATION_DISABLED)

    def test_n8n_response_validation_rejects_missing_success(self):
        """HTTP 200 is not enough without the response contract."""
        request = IntegrationRequest(workflow_key="system.echo", action="system.echo", request_id="IR-test")
        provider = N8nBridgeProvider(
            config=N8nConfig(provider="n8n", bridge_enabled=True, base_url="https://n8n.example", api_token="token"),
            client=FakeClient(status=200, response={"request_id": "IR-test", "action": "system.echo"}),
        )
        result = provider.execute(request)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, INVALID_RESPONSE)

    def test_ability_metadata_is_integration_and_registered(self):
        """Integration Ability keeps Native and Integration boundaries distinct."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        registry = AbilityRegistry()
        registry.register(ability)

        self.assertEqual(ability.metadata.type.value, "integration")
        self.assertEqual(ability.metadata.permission, PermissionLevel.SAFE)
        self.assertIn("notification.test", registry.list_capabilities("integration_n8n"))

    def test_ability_system_health_uses_mock_bridge(self):
        """Ability executes a safe workflow through the bridge."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute({"workflow_key": "system.health", "action": "system.health"})

        self.assertIsInstance(result, AbilityResult)
        self.assertTrue(result.success)
        self.assertIn("정상", result.to_natural_language())

    def test_confirm_required_workflow_returns_pending_metadata(self):
        """Confirm workflows use existing pending action shape."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute({"workflow_key": "notification.test", "action": "notification.test"})

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["permission"], "confirm_required")
        self.assertEqual(result.metadata["query"].workflow_key, "notification.test")

    def test_confirmed_workflow_executes(self):
        """Confirmed notification.test workflow executes through the bridge."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute(
            {
                "workflow_key": "notification.test",
                "action": "notification.test",
                "payload": {"message": "hello"},
                "_confirmed": True,
            }
        )

        self.assertTrue(result.success)
        self.assertIn("테스트 알림", result.to_natural_language())

    def test_dispatcher_routes_integration_ability(self):
        """Runtime Dispatcher can execute the Integration Ability adapter."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        result = dispatcher.execute(
            ToolRequest(
                tool_name="integration_n8n",
                input_data={"workflow_key": "system.echo", "action": "system.echo", "payload": {"message": "hi"}},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output.data.data["echo"], "hi")

    def test_correlation_ids_are_preserved(self):
        """Request/result keep conversation, session, request, and workflow IDs."""
        request = IntegrationRequest(
            workflow_key="system.echo",
            action="system.echo",
            payload={"message": "hello"},
            conversation_id="conv-1",
            session_id="session-1",
            request_id="request-1",
            workflow_id="workflow-1",
        )
        result = MockIntegrationBridge().execute(request)

        self.assertTrue(result.success)
        self.assertEqual(result.conversation_id, "conv-1")
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.request_id, "request-1")
        self.assertEqual(result.workflow_id, "workflow-1")

    def test_ability_result_preserves_correlation_ids(self):
        """Ability output keeps bridge correlation IDs visible."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute(
            {
                "workflow_key": "system.echo",
                "action": "system.echo",
                "payload": {"message": "hello"},
                "conversation_id": "conv-ability",
                "session_id": "session-ability",
                "workflow_id": "workflow-ability",
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data.conversation_id, "conv-ability")
        self.assertEqual(result.data.session_id, "session-ability")
        self.assertEqual(result.data.workflow_id, "workflow-ability")
        self.assertTrue(result.data.request_id.startswith("IR-"))

    def test_retry_policy_contract_is_in_payload(self):
        """Retry policy is part of the request contract even before execution retry."""
        request = IntegrationRequest(
            workflow_key="system.echo",
            action="system.echo",
            max_retry=2,
            retry_delay_seconds=0.5,
        )
        payload = create_http_payload(request)

        self.assertEqual(payload["retry"]["max_retry"], 2)
        self.assertEqual(payload["retry"]["retry_delay_seconds"], 0.5)

    def test_provider_capabilities_are_exposed(self):
        """Providers expose stable capability metadata."""
        provider = MockIntegrationBridge()

        self.assertTrue(provider.capabilities.health)
        self.assertTrue(provider.capabilities.execute)
        self.assertTrue(provider.capabilities.supports_confirmation)
        self.assertFalse(provider.capabilities.supports_stream)
        self.assertFalse(provider.capabilities.supports_async)

    def test_integration_metrics_record_success_and_failure(self):
        """Provider metrics track success, failure, and average latency."""
        provider = MockIntegrationBridge()
        start_success = provider.metrics.success_count
        start_failed = provider.metrics.failed_count
        provider.execute(IntegrationRequest(workflow_key="system.echo", action="system.echo"))
        provider.execute(IntegrationRequest(workflow_key="unknown.workflow", action="unknown.workflow"))

        self.assertGreaterEqual(provider.metrics.success_count, start_success + 1)
        self.assertGreaterEqual(provider.metrics.failed_count, start_failed + 1)
        self.assertGreaterEqual(provider.metrics.average_latency_ms, 0)

    def test_timeout_metrics_are_recorded(self):
        """Timeout failures increment the timeout metric."""
        provider = N8nBridgeProvider(
            config=N8nConfig(provider="n8n", bridge_enabled=True, base_url="https://n8n.example", api_token="token"),
            client=FailingClient(TIMEOUT, "timed out"),
        )
        start_timeout = provider.metrics.timeout_count
        result = provider.execute(IntegrationRequest(workflow_key="system.echo", action="system.echo"))

        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertEqual(result.error_code, TIMEOUT)
        self.assertGreaterEqual(provider.metrics.timeout_count, start_timeout + 1)

    def test_korean_integration_health_aliases_route_to_system_health(self):
        """Korean voice-friendly aliases route to system.health."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        examples = [
            "맨발은 연결 상태 확인해 줘",
            "nam 연결 상태 확인해 줘",
            "외부 자동화 연결 상태 확인해줘",
            "외부 자동화 연결 확인해 줘",
            "자동화 브리지 상태 확인해줘",
            "연동 상태 확인해줘",
            "외부 서비스 연결 상태 확인해줘",
        ]

        for text in examples:
            with self.subTest(text=text):
                result = ability.execute({"text": text})
                self.assertTrue(result.success)
                self.assertEqual(result.metadata["query"].workflow_key, "system.health")

    def test_dispatcher_selects_integration_for_korean_health_alias(self):
        """Runtime routing selects integration_n8n for Korean bridge health text."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        result = dispatcher.execute_text("연동 상태 확인해줘")

        self.assertTrue(result.success)
        self.assertEqual(result.selected.tool_name, "integration_n8n")
        self.assertEqual(result.tool_result.output.data.workflow_key, "system.health")

    def test_dispatcher_selects_integration_when_status_word_is_omitted(self):
        """Bridge health routing works even when the user omits 'status'."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        result = dispatcher.execute_text("외부 자동화 연결 확인해 줘")

        self.assertTrue(result.success)
        self.assertEqual(result.selected.tool_name, "integration_n8n")
        self.assertEqual(result.tool_result.output.data.workflow_key, "system.health")

    def test_korean_integration_echo_request_routes_to_system_echo(self):
        """Voice-friendly n8n send requests route to system.echo."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute({"text": "n8n 자동화로 안녕하세요를 보내 줘"})

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["query"].workflow_key, "system.echo")
        self.assertEqual(result.metadata["query"].payload["message"], "안녕하세요")
        self.assertEqual(result.to_natural_language(), "안녕하세요")

    def test_dispatcher_selects_integration_for_korean_echo_request(self):
        """Runtime routing avoids LLM fallback for n8n send requests."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        result = dispatcher.execute_text("n8n 자동화로 안녕하세요를 보내 줘")

        self.assertTrue(result.success)
        self.assertEqual(result.selected.tool_name, "integration_n8n")
        self.assertEqual(result.tool_result.output.data.workflow_key, "system.echo")

    def test_system_echo_korean_aliases_route_to_system_echo(self):
        """Korean spoken system.echo aliases route to system.echo."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        examples = [
            "\uc2dc\uc2a4\ud15c\uc5d0\ucf54 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
            "\uc2dc\uc2a4\ud15c \uc5d0\ucf54 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
            "\uc2dc\uc2a4\ud15c\uc810\uc5d0\ucf54 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
            "\uc2dc\uc2a4\ud15c\uc9ec\uc5d0\ucf54 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
            "\uc2dc\uc2a4\ud15c \ub9e5\ud3ec \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
            "\uc2dc\uc2a4\ud15c \ud558\uace0 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
            "\uc2dc\uc2a4\ud15c4 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918",
        ]

        for text in examples:
            with self.subTest(text=text):
                result = ability.execute({"text": text})
                self.assertTrue(result.success)
                self.assertEqual(result.metadata["query"].workflow_key, "system.echo")
                self.assertEqual(result.metadata["query"].payload["message"], "\uc548\ub155\ud558\uc138\uc694")

    def test_dispatcher_prefix_system_echo_executes_workflow(self):
        """Prefix routing for system.echo keeps the workflow key."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        result = dispatcher.execute_text("system.echo \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")

        self.assertTrue(result.success)
        self.assertEqual(result.selected.tool_name, "integration_n8n")
        self.assertEqual(result.tool_result.output.data.workflow_key, "system.echo")
        self.assertEqual(result.tool_result.output.data.data["echo"], "\uc548\ub155\ud558\uc138\uc694")

    def test_n8n_status_routes_to_system_health(self):
        """n8n status phrases route to health."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute({"text": "n8n \uc0c1\ud0dc \ud655\uc778\ud574 \uc918"})

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["query"].workflow_key, "system.health")

    def test_n8n_currency_alias_routes_to_system_health(self):
        """Currency-looking n8n STT mistake routes to health."""
        ability = N8nIntegrationAbility(bridge=MockIntegrationBridge())
        result = ability.execute({"text": "\uc5d4\ud654\ub97c \uc0c1\ud0dc \ud655\uc778\ud574 \uc918"})

        self.assertTrue(result.success)
        self.assertEqual(result.metadata["query"].workflow_key, "system.health")

    def test_dispatcher_handles_common_stt_misrecognitions_for_integration(self):
        """Common voice mistakes still route to Integration workflows."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)

        health = dispatcher.execute_text("외부 자동차 연결 상태 확인해 줘")
        echo = dispatcher.execute_text("nan 자동화로 안녕하세요를 보내 줘")

        self.assertTrue(health.success)
        self.assertEqual(health.selected.tool_name, "integration_n8n")
        self.assertEqual(health.tool_result.output.data.workflow_key, "system.health")
        self.assertTrue(echo.success)
        self.assertEqual(echo.selected.tool_name, "integration_n8n")
        self.assertEqual(echo.tool_result.output.data.workflow_key, "system.echo")
        self.assertEqual(echo.tool_result.output.data.data["echo"], "안녕하세요")

    def test_dispatcher_selects_integration_for_ambiguous_workflow_execute(self):
        """Ambiguous workflow commands ask for a workflow instead of falling back to LLM."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(N8nIntegrationAbility(bridge=MockIntegrationBridge()))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        result = dispatcher.execute_text("n8n 워크플로우 실행해 줘")

        self.assertFalse(result.success)
        self.assertEqual(result.selected.tool_name, "integration_n8n")
        self.assertEqual(
            result.tool_result.output.to_natural_language(),
            "어떤 workflow를 실행할까요? 예를 들어 상태 확인, 테스트 알림, system.echo처럼 말씀해 주세요.",
        )


class FakeClient:
    """Fake n8n client for validation tests."""

    def __init__(self, status, response):
        self.status = status
        self.response = response

    def post_workflow(self, url, payload, timeout_seconds, headers=None):
        return self.status, self.response


class FailingClient:
    """Fake n8n client that raises a transport error."""

    def __init__(self, code, message):
        self.code = code
        self.message = message

    def post_workflow(self, url, payload, timeout_seconds, headers=None):
        raise IntegrationTransportError(self.code, self.message)


if __name__ == "__main__":
    unittest.main()
