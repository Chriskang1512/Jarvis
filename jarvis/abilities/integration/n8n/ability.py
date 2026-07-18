import json
from pathlib import Path

from jarvis.abilities.integration.n8n.parser import N8nIntegrationParser
from jarvis.abilities.integration.n8n.query import IntegrationQuery
from jarvis.abilities.integration.n8n.result import N8nAbilityResult
from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.debug_trace import trace_event
from jarvis.integrations.bridge import IntegrationRequest
from jarvis.integrations.bridge.errors import WORKFLOW_NOT_FOUND
from jarvis.integrations.n8n import WorkflowRegistry, create_integration_bridge
from jarvis.permissions import PermissionLevel


class N8nIntegrationAbility:
    """Integration Ability that executes allowed workflows through a bridge."""

    def __init__(self, bridge=None, workflow_registry=None, metadata=None, parser=None):
        """Create n8n Integration Ability."""
        self.workflow_registry = workflow_registry or WorkflowRegistry()
        self.bridge = bridge or create_integration_bridge(registry=self.workflow_registry)
        self.metadata = metadata or load_integration_metadata()
        self.parser = parser or N8nIntegrationParser()

    @property
    def id(self):
        """Return ability ID."""
        return self.metadata.id

    @property
    def name(self):
        """Return ability name."""
        return self.metadata.name

    @property
    def type(self):
        """Return ability type."""
        return self.metadata.type

    @property
    def description(self):
        """Return ability description."""
        return self.metadata.description

    @property
    def permission(self):
        """Return base ability permission."""
        return self.metadata.permission

    def execute(self, input_data):
        """Execute one integration workflow."""
        try:
            query = normalize_query(input_data, self.parser)
            workflow = self.workflow_registry.get(query.workflow_key)
            trace_event(
                "integration.request",
                workflow=query.workflow_key,
                action=query.action,
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                request_id="",
                workflow_id=query.workflow_id or query.workflow_key,
            )

            if workflow is None or not workflow.enabled:
                result = N8nAbilityResult(
                    success=False,
                    workflow_key=query.workflow_key,
                    action=query.action,
                    provider=getattr(self.bridge, "provider_name", ""),
                    error_code=WORKFLOW_NOT_FOUND,
                    error_message="등록되지 않은 workflow입니다.",
                )
                return AbilityResult(success=False, data=result, error=result.to_natural_language(), metadata={"ability_id": self.id})

            trace_event("integration.permission", workflow=query.workflow_key, permission=workflow.permission.value)

            if workflow.permission == PermissionLevel.CONFIRM and not is_confirmed(input_data):
                return AbilityResult(
                    success=True,
                    data=N8nAbilityResult(
                        success=True,
                        workflow_key=query.workflow_key,
                        action=query.action,
                        provider=getattr(self.bridge, "provider_name", ""),
                        message="n8n 테스트 workflow를 실행하려고 합니다. 실행할까요?",
                    ),
                    metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                )

            request = IntegrationRequest(
                workflow_key=query.workflow_key,
                action=query.action,
                payload=dict(query.payload),
                permission=workflow.permission.value,
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                workflow_id=query.workflow_id or query.workflow_key,
                idempotency_key=query.idempotency_key,
                timeout_seconds=workflow.timeout_seconds,
                max_retry=query.max_retry or workflow.max_retry,
                retry_delay_seconds=query.retry_delay_seconds or workflow.retry_delay_seconds,
                metadata=dict(query.metadata),
            )
            bridge_result = self.bridge.execute(request)
            result = N8nAbilityResult(
                success=bridge_result.success,
                workflow_key=bridge_result.workflow_key,
                action=bridge_result.action,
                provider=bridge_result.provider,
                conversation_id=bridge_result.conversation_id,
                session_id=bridge_result.session_id,
                request_id=bridge_result.request_id,
                workflow_id=bridge_result.workflow_id,
                message=bridge_result.message,
                data=dict(bridge_result.data),
                error_code=bridge_result.error_code,
                error_message=bridge_result.error_message,
            )
            return AbilityResult(
                success=result.success,
                data=result,
                error="" if result.success else result.to_natural_language(),
                metadata={"ability_id": self.id, "provider": result.provider, "query": query},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    def health(self):
        """Return provider health."""
        if hasattr(self.bridge, "health"):
            health = self.bridge.health()
            status = "ok" if health.ok else "error"
            return AbilityHealth(status=status, provider=health.provider, message=health.error)

        return AbilityHealth(status="error", provider="", message="Integration bridge has no health method.")


def load_integration_metadata():
    """Load n8n Integration manifest."""
    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return AbilityMetadata(
        id=manifest["id"],
        name=manifest["name"],
        type=AbilityType(manifest["type"]),
        permission=PermissionLevel(manifest["permission"]),
        version=manifest["version"],
        author=manifest.get("author", "Jarvis"),
        description=manifest["description"],
        capabilities=list(manifest.get("capabilities", [])),
        input_schema=dict(manifest.get("input_schema", {})),
        output_schema=manifest.get("output_schema", "N8nAbilityResult"),
        provider="n8n",
        priority="normal",
        aliases=["n8n", "integration", "workflow", "system.echo", "system.health", "notification.test", "테스트 알림", "알림 테스트"],
        supported_intents=["n8n 상태", "n8n health", "system.echo", "system.health", "notification.test", "테스트 알림"],
        examples=["n8n 상태 확인해줘", "system.echo hello", "테스트 알림 보내줘"],
        input_prefixes=["n8n", "system.echo", "system.health", "notification.test", "echo", "에코"],
        route_confidence=0.75,
    )


def normalize_query(input_data, parser=None):
    """Return IntegrationQuery from direct input or free text."""
    if hasattr(input_data, "workflow_key") and hasattr(input_data, "action"):
        return input_data

    if isinstance(input_data, dict) and "workflow_key" in input_data:
        return IntegrationQuery(
            workflow_key=str(input_data.get("workflow_key", "")),
            action=str(input_data.get("action", input_data.get("workflow_key", ""))),
            payload=dict(input_data.get("payload", {}) or {}),
            raw_text=str(input_data.get("raw_text", input_data.get("text", ""))),
            conversation_id=str(input_data.get("conversation_id", "")),
            session_id=str(input_data.get("session_id", "")),
            workflow_id=str(input_data.get("workflow_id", "")),
            idempotency_key=str(input_data.get("idempotency_key", "")),
            max_retry=int(input_data.get("max_retry", 0) or 0),
            retry_delay_seconds=float(input_data.get("retry_delay_seconds", 0.0) or 0.0),
            metadata=dict(input_data.get("metadata", {}) or {}),
        )

    parser = parser or N8nIntegrationParser()
    raw_text = ""

    if isinstance(input_data, dict):
        raw_text = input_data.get("text") or input_data.get("raw_text") or input_data.get("key") or ""
    else:
        raw_text = str(input_data or "")

    return parser.parse(raw_text)


def is_confirmed(input_data):
    """Return whether the integration action was confirmed."""
    if not isinstance(input_data, dict):
        return False

    return bool(input_data.get("_confirmed", input_data.get("confirmed", False)))


_LegacyN8nIntegrationAbility = N8nIntegrationAbility


class N8nIntegrationAbility(_LegacyN8nIntegrationAbility):
    """Integration Ability with clean Korean runtime responses."""

    def execute(self, input_data):
        """Execute one integration workflow."""
        try:
            query = normalize_query(input_data, self.parser)
            workflow = self.workflow_registry.get(query.workflow_key)
            trace_event(
                "integration.request",
                workflow=query.workflow_key,
                action=query.action,
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                request_id="",
                workflow_id=query.workflow_id or query.workflow_key,
            )

            if workflow is None or not workflow.enabled:
                message = "어떤 workflow를 실행할까요? 예를 들어 상태 확인, 테스트 알림, system.echo처럼 말씀해 주세요." if query.workflow_key == "" else "등록되지 않은 workflow입니다."
                result = N8nAbilityResult(
                    success=False,
                    workflow_key=query.workflow_key,
                    action=query.action,
                    provider=getattr(self.bridge, "provider_name", ""),
                    error_code=WORKFLOW_NOT_FOUND,
                    error_message=message,
                )
                return AbilityResult(success=False, data=result, error=message, metadata={"ability_id": self.id, "query": query})

            trace_event("integration.permission", workflow=query.workflow_key, permission=workflow.permission.value)

            if workflow.permission == PermissionLevel.CONFIRM and not is_confirmed(input_data):
                return AbilityResult(
                    success=True,
                    data=N8nAbilityResult(
                        success=True,
                        workflow_key=query.workflow_key,
                        action=query.action,
                        provider=getattr(self.bridge, "provider_name", ""),
                        message="n8n 테스트 workflow를 실행하려고 합니다. 실행할까요?",
                    ),
                    metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                )

            request = IntegrationRequest(
                workflow_key=query.workflow_key,
                action=query.action,
                payload=dict(query.payload),
                permission=workflow.permission.value,
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                workflow_id=query.workflow_id or query.workflow_key,
                idempotency_key=query.idempotency_key,
                timeout_seconds=workflow.timeout_seconds,
                max_retry=query.max_retry or workflow.max_retry,
                retry_delay_seconds=query.retry_delay_seconds or workflow.retry_delay_seconds,
                metadata=dict(query.metadata),
            )
            bridge_result = self.bridge.execute(request)
            result = N8nAbilityResult(
                success=bridge_result.success,
                workflow_key=bridge_result.workflow_key,
                action=bridge_result.action,
                provider=bridge_result.provider,
                conversation_id=bridge_result.conversation_id,
                session_id=bridge_result.session_id,
                request_id=bridge_result.request_id,
                workflow_id=bridge_result.workflow_id,
                message=bridge_result.message,
                data=dict(bridge_result.data),
                error_code=bridge_result.error_code,
                error_message=bridge_result.error_message,
            )
            return AbilityResult(
                success=result.success,
                data=result,
                error="" if result.success else result.to_natural_language(),
                metadata={"ability_id": self.id, "provider": result.provider, "query": query},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})


_PreviousCleanN8nIntegrationAbility = N8nIntegrationAbility


class N8nIntegrationAbility(_PreviousCleanN8nIntegrationAbility):
    """Integration Ability with stable Korean runtime responses."""

    def execute(self, input_data):
        """Execute one integration workflow."""
        try:
            query = normalize_query(input_data, self.parser)
            workflow = self.workflow_registry.get(query.workflow_key)
            trace_event(
                "integration.request",
                workflow=query.workflow_key,
                action=query.action,
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                request_id="",
                workflow_id=query.workflow_id or query.workflow_key,
            )

            if workflow is None or not workflow.enabled:
                message = (
                    "\uc5b4\ub5a4 workflow\ub97c \uc2e4\ud589\ud560\uae4c\uc694? "
                    "\uc608\ub97c \ub4e4\uc5b4 \uc0c1\ud0dc \ud655\uc778, \ud14c\uc2a4\ud2b8 \uc54c\ub9bc, system.echo\ucc98\ub7fc \ub9d0\uc500\ud574 \uc8fc\uc138\uc694."
                    if query.workflow_key == ""
                    else "\ub4f1\ub85d\ub418\uc9c0 \uc54a\uc740 workflow\uc785\ub2c8\ub2e4."
                )
                result = N8nAbilityResult(
                    success=False,
                    workflow_key=query.workflow_key,
                    action=query.action,
                    provider=getattr(self.bridge, "provider_name", ""),
                    error_code=WORKFLOW_NOT_FOUND,
                    error_message=message,
                )
                return AbilityResult(success=False, data=result, error=message, metadata={"ability_id": self.id, "query": query})

            trace_event("integration.permission", workflow=query.workflow_key, permission=workflow.permission.value)

            if workflow.permission == PermissionLevel.CONFIRM and not is_confirmed(input_data):
                return AbilityResult(
                    success=True,
                    data=N8nAbilityResult(
                        success=True,
                        workflow_key=query.workflow_key,
                        action=query.action,
                        provider=getattr(self.bridge, "provider_name", ""),
                        message="n8n \ud14c\uc2a4\ud2b8 workflow\ub97c \uc2e4\ud589\ud558\ub824\uace0 \ud569\ub2c8\ub2e4. \uc2e4\ud589\ud560\uae4c\uc694?",
                    ),
                    metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                )

            request = IntegrationRequest(
                workflow_key=query.workflow_key,
                action=query.action,
                payload=dict(query.payload),
                permission=workflow.permission.value,
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                workflow_id=query.workflow_id or query.workflow_key,
                idempotency_key=query.idempotency_key,
                timeout_seconds=workflow.timeout_seconds,
                max_retry=query.max_retry or workflow.max_retry,
                retry_delay_seconds=query.retry_delay_seconds or workflow.retry_delay_seconds,
                metadata=dict(query.metadata),
            )
            bridge_result = self.bridge.execute(request)
            result = N8nAbilityResult(
                success=bridge_result.success,
                workflow_key=bridge_result.workflow_key,
                action=bridge_result.action,
                provider=bridge_result.provider,
                conversation_id=bridge_result.conversation_id,
                session_id=bridge_result.session_id,
                request_id=bridge_result.request_id,
                workflow_id=bridge_result.workflow_id,
                message=bridge_result.message,
                data=dict(bridge_result.data),
                error_code=bridge_result.error_code,
                error_message=bridge_result.error_message,
            )
            return AbilityResult(
                success=result.success,
                data=result,
                error="" if result.success else result.to_natural_language(),
                metadata={"ability_id": self.id, "provider": result.provider, "query": query},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})
