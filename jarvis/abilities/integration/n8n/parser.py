from jarvis.abilities.integration.n8n.query import IntegrationQuery


class N8nIntegrationParser:
    """Rule parser for Sprint 7 foundation workflows."""

    def parse(self, text):
        """Parse free text into an IntegrationQuery when possible."""
        raw_text = str(text or "").strip()
        normalized = " ".join(raw_text.lower().split())

        if normalized == "":
            return IntegrationQuery(workflow_key="", action="", raw_text=raw_text)

        if is_nam_health_alias(normalized):
            return IntegrationQuery(
                workflow_key="system.health",
                action="system.health",
                payload={},
                raw_text=raw_text,
            )

        if is_system_health_alias(normalized):
            return IntegrationQuery(
                workflow_key="system.health",
                action="system.health",
                payload={},
                raw_text=raw_text,
            )

        if "system.health" in normalized or "n8n" in normalized and any(token in normalized for token in ["health", "상태", "헬스"]):
            return IntegrationQuery(
                workflow_key="system.health",
                action="system.health",
                payload={},
                raw_text=raw_text,
            )

        if "system.echo" in normalized or normalized.startswith("echo ") or normalized.startswith("에코 "):
            message = cleanup_echo_message(raw_text)
            return IntegrationQuery(
                workflow_key="system.echo",
                action="system.echo",
                payload={"message": message},
                raw_text=raw_text,
            )

        if any(token in normalized for token in ["notification.test", "테스트 알림", "알림 테스트"]):
            return IntegrationQuery(
                workflow_key="notification.test",
                action="notification.test",
                payload={"message": "테스트 알림입니다."},
                raw_text=raw_text,
            )

        return IntegrationQuery(workflow_key="", action="", raw_text=raw_text)


def cleanup_echo_message(text):
    """Remove echo command tokens from text."""
    value = str(text or "").strip()

    for prefix in ["system.echo", "echo", "에코", "n8n echo"]:
        if value.lower().startswith(prefix):
            return value[len(prefix):].strip()

    return value


def is_nam_health_alias(text):
    """Return whether nam was likely a misrecognized n8n health request."""
    normalized = str(text or "").lower()

    if "nam" not in normalized:
        return False

    return any(token in normalized for token in ["연결", "상태", "확인", "health"])


def is_system_health_alias(text):
    """Return whether text asks for integration bridge health."""
    normalized = str(text or "").lower()

    n8n_aliases = ["n8n", "맨발은", "엔에잇엔", "엔팔엔"]
    health_tokens = ["health", "상태", "헬스", "연결"]

    if any(alias in normalized for alias in n8n_aliases) and any(token in normalized for token in health_tokens):
        return True

    if is_loose_integration_health_match(normalized):
        return True

    health_phrases = [
        "외부 자동화 연결 상태 확인해줘",
        "외부 자동화 연결 상태 확인해 줘",
        "자동화 브리지 상태 확인해줘",
        "자동화 브리지 상태 확인해 줘",
        "연동 상태 확인해줘",
        "연동 상태 확인해 줘",
        "외부 서비스 연결 상태 확인해줘",
        "외부 서비스 연결 상태 확인해 줘",
    ]
    return any(phrase in normalized for phrase in health_phrases)


def is_loose_integration_health_match(text):
    """Return whether text is a natural Korean integration-health request."""
    normalized = str(text or "").lower()
    subjects = [
        "\uc678\ubd80 \uc790\ub3d9\ud654",
        "\uc790\ub3d9\ud654 \ube0c\ub9ac\uc9c0",
        "\ube0c\ub9ac\uc9c0",
        "\uc5f0\ub3d9",
        "\uc678\ubd80 \uc11c\ube44\uc2a4",
        "\uc11c\ube44\uc2a4",
    ]
    action_tokens = ["\uc5f0\uacb0", "\uc0c1\ud0dc", "\ud655\uc778", "health"]

    return any(subject in normalized for subject in subjects) and any(token in normalized for token in action_tokens)


# Clean parser override. Some early Sprint 7 strings were saved with a broken
# console encoding; keep the public class name stable while matching real Korean
# voice input and common STT aliases.
import re as _re


N8N_ALIASES_CLEAN = ["n8n", "맨발은", "엔에잇엔", "엔팔엔", "nam", "nan", "n8"]
INTEGRATION_SUBJECTS_CLEAN = N8N_ALIASES_CLEAN + [
    "외부 자동화",
    "외부 자동차",
    "자동화",
    "자동차",
    "자동화 브리지",
    "브리지",
    "연동",
    "외부 서비스",
    "워크플로우",
]
LOOSE_HEALTH_SUBJECTS_CLEAN = ["외부 자동화", "외부 자동차", "자동화 브리지", "브리지", "연동", "외부 서비스", "서비스"]
HEALTH_TOKENS_CLEAN = ["health", "상태", "헬스", "연결", "확인"]
SEND_TOKENS_CLEAN = ["보내", "보내줘", "보여", "보여줘", "전송", "전송해", "메시지"]
WORKFLOW_TOKENS_CLEAN = ["workflow", "워크플로우", "자동화"]
EXECUTE_TOKENS_CLEAN = ["실행", "실행해", "돌려", "시작"]


class N8nIntegrationParser:
    """Rule parser for Sprint 7 foundation workflows."""

    def parse(self, text):
        """Parse free text into an IntegrationQuery when possible."""
        raw_text = str(text or "").strip()
        normalized = normalize_clean(raw_text)

        if normalized == "":
            return IntegrationQuery(workflow_key="", action="", raw_text=raw_text)

        if is_system_health_alias_clean(normalized):
            return IntegrationQuery(workflow_key="system.health", action="system.health", payload={}, raw_text=raw_text)

        if is_echo_request_clean(normalized):
            return IntegrationQuery(
                workflow_key="system.echo",
                action="system.echo",
                payload={"message": cleanup_echo_message_clean(raw_text)},
                raw_text=raw_text,
            )

        if is_notification_test_request_clean(normalized):
            return IntegrationQuery(
                workflow_key="notification.test",
                action="notification.test",
                payload={"message": "테스트 알림입니다."},
                raw_text=raw_text,
            )

        return IntegrationQuery(workflow_key="", action="", raw_text=raw_text)


def normalize_clean(text):
    """Normalize spacing and case for parser matching."""
    return " ".join(str(text or "").lower().split())


def cleanup_echo_message_clean(text):
    """Remove echo command tokens from text."""
    value = str(text or "").strip()
    lower_value = value.lower()

    for prefix in ["system.echo", "echo", "에코", "n8n echo"]:
        if lower_value.startswith(prefix):
            value = value[len(prefix):].strip()
            break

    value = strip_n8n_aliases_clean(value)
    value = _re.sub(r"^\s*(자동화|외부\s*자동화|워크플로우)\s*(로|으로)?\s*", "", value)
    value = _re.sub(r"\s*(보내\s*줘|보내줘|보여\s*줘|보여줘|전송해\s*줘|전송해줘|실행해\s*줘|실행해줘)\s*$", "", value)
    value = value.strip()

    if len(value) > 1 and value[-1] in ("을", "를"):
        value = value[:-1].strip()

    return value


def strip_n8n_aliases_clean(text):
    """Strip leading n8n aliases while preserving the user payload."""
    value = str(text or "").strip()

    for alias in N8N_ALIASES_CLEAN:
        pattern = _re.compile(rf"^\s*{_re.escape(alias)}\s*(은|는|으로|로)?\s*", _re.IGNORECASE)
        value = pattern.sub("", value)

    return value.strip()


def is_system_health_alias_clean(text):
    """Return whether text asks for integration bridge health."""
    normalized = normalize_clean(text)

    if any(alias in normalized for alias in N8N_ALIASES_CLEAN) and any(token in normalized for token in HEALTH_TOKENS_CLEAN):
        return True

    return is_loose_integration_health_match_clean(normalized)


def is_echo_request_clean(text):
    """Return whether text asks the bridge to send/echo a message."""
    normalized = normalize_clean(text)

    if "system.echo" in normalized or normalized.startswith("echo ") or normalized.startswith("에코 "):
        return True

    if not any(alias in normalized for alias in INTEGRATION_SUBJECTS_CLEAN):
        return False

    return any(token in normalized for token in SEND_TOKENS_CLEAN)


def is_notification_test_request_clean(text):
    """Return whether text asks for the built-in notification test workflow."""
    normalized = normalize_clean(text)
    return any(token in normalized for token in ["notification.test", "테스트 알림", "알림 테스트"])


def is_loose_integration_health_match_clean(text):
    """Return whether text is a natural Korean integration-health request."""
    normalized = normalize_clean(text)
    return any(subject in normalized for subject in LOOSE_HEALTH_SUBJECTS_CLEAN) and any(token in normalized for token in HEALTH_TOKENS_CLEAN)


def is_integration_workflow_request(text):
    """Return whether text is an integration request even before a workflow is known."""
    normalized = normalize_clean(text)

    if is_system_health_alias_clean(normalized) or is_echo_request_clean(normalized) or is_notification_test_request_clean(normalized):
        return True

    if any(alias in normalized for alias in INTEGRATION_SUBJECTS_CLEAN):
        return any(token in normalized for token in WORKFLOW_TOKENS_CLEAN + EXECUTE_TOKENS_CLEAN + SEND_TOKENS_CLEAN)

    return False


# Final parser pass. Keep this ASCII-safe so Korean aliases do not depend on the
# terminal code page used to edit or display the file.
N8N_ALIASES_FINAL = [
    "n8n",
    "nam",
    "nan",
    "n8",
    "namm",
    "na",
    "\ub9e8\ubc1c\uc740",
    "\uc5d4\uc5d0\uc787\uc5d4",
    "\uc5d4\ud314\uc5d4",
    "\uc5d4\ud654\ub97c",
    "\uc5d4\ud654\ub294",
    "\uc5d4\ud654",
]
HEALTH_TOKENS_FINAL = ["health", "\uc0c1\ud0dc", "\ud5ec\uc2a4", "\uc5f0\uacb0", "\ud655\uc778"]
SEND_TOKENS_FINAL = ["\ubcf4\ub0b4", "\ubcf4\ub0b4\uc918", "\ubcf4\uc5ec", "\ubcf4\uc5ec\uc918", "\uc804\uc1a1", "\uba54\uc2dc\uc9c0"]
EXECUTE_TOKENS_FINAL = ["\uc2e4\ud589", "\uc9c4\ud589", "\uc2dc\uc791"]
WORKFLOW_TOKENS_FINAL = ["workflow", "\uc6cc\ud06c\ud50c\ub85c\uc6b0", "\uc6cc\ud06c \ud50c\ub85c\uc6b0", "walk flo", "work flo"]
INTEGRATION_SUBJECTS_FINAL = N8N_ALIASES_FINAL + [
    "\uc678\ubd80 \uc790\ub3d9\ud654",
    "\uc678\ubd80 \uc790\ub3d9\ucc28",
    "\uc790\ub3d9\ud654",
    "\uc790\ub3d9\ucc28",
    "\uc790\ub3d9\ud654 \ube0c\ub9ac\uc9c0",
    "\ube0c\ub9ac\uc9c0",
    "\uc5f0\ub3d9",
    "\uc678\ubd80 \uc11c\ube44\uc2a4",
    "\uc6cc\ud06c\ud50c\ub85c\uc6b0",
    "workflow",
]
SYSTEM_ECHO_ALIASES_FINAL = [
    "system.echo",
    "system echo",
    "\uc2dc\uc2a4\ud15c\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c \uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c\uc810\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c\uc9ec\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c \uc810 \uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c \uc9ec \uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c.\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c\ub9e5\ud3ec",
    "\uc2dc\uc2a4\ud15c \ub9e5\ud3ec",
    "\uc2dc\uc2a4\ud15c\ud558\uace0",
    "\uc2dc\uc2a4\ud15c \ud558\uace0",
    "\uc2dc\uc2a4\ud15c4",
    "\uc2dc\uc2a4\ud15c 4",
]
NOTIFICATION_TEST_ALIASES_FINAL = ["notification.test", "\ud14c\uc2a4\ud2b8 \uc54c\ub9bc", "\uc54c\ub9bc \ud14c\uc2a4\ud2b8"]


class N8nIntegrationParser:
    """Rule parser for Sprint 7 foundation workflows."""

    def parse(self, text):
        """Parse free text into an IntegrationQuery when possible."""
        raw_text = str(text or "").strip()
        normalized = normalize_final(raw_text)

        if normalized == "":
            return IntegrationQuery(workflow_key="", action="", raw_text=raw_text)

        if is_system_health_alias_final(normalized):
            return IntegrationQuery(workflow_key="system.health", action="system.health", payload={}, raw_text=raw_text)

        if is_echo_request_final(normalized):
            return IntegrationQuery(
                workflow_key="system.echo",
                action="system.echo",
                payload={"message": cleanup_echo_message_final(raw_text)},
                raw_text=raw_text,
            )

        if is_notification_test_request_final(normalized):
            return IntegrationQuery(
                workflow_key="notification.test",
                action="notification.test",
                payload={"message": "\ud14c\uc2a4\ud2b8 \uc54c\ub9bc\uc785\ub2c8\ub2e4."},
                raw_text=raw_text,
            )

        return IntegrationQuery(workflow_key="", action="", raw_text=raw_text)


def normalize_final(text):
    """Normalize spacing and common STT spellings."""
    normalized = " ".join(str(text or "").lower().split())
    normalized = normalized.replace("walk flo", "workflow").replace("work flo", "workflow")
    normalized = normalized.replace("walk flow", "workflow").replace("work flow", "workflow")
    return normalized


def compact_final(text):
    """Return a compact comparison form."""
    return normalize_final(text).replace(" ", "").replace(".", "")


def has_any_final(text, values):
    """Return whether any value appears in text or compact text."""
    normalized = normalize_final(text)
    compact = compact_final(text)

    for value in values:
        normalized_value = normalize_final(value)
        compact_value = compact_final(value)

        if normalized_value and normalized_value in normalized:
            return True

        if compact_value and compact_value in compact:
            return True

    return False


def is_system_health_alias_final(text):
    """Return whether text asks for integration bridge health."""
    normalized = normalize_final(text)
    compact = compact_final(text)

    if has_any_final(normalized, N8N_ALIASES_FINAL) and has_any_final(normalized, HEALTH_TOKENS_FINAL):
        return True

    if compact in ["\uc0c1\ud0dc\ud655\uc778", "\uc5f0\uacb0\uc0c1\ud0dc\ud655\uc778"]:
        return True

    return has_any_final(
        normalized,
        [
            "\uc5f0\ub3d9",
            "\uc678\ubd80 \uc790\ub3d9\ud654",
            "\uc678\ubd80\uc790\ub3d9\ud654",
            "\uc678\ubd80 \uc790\ub3d9\ucc28",
            "\uc678\ubd80\uc790\ub3d9\ucc28",
            "\uc678\ubd80 \uc11c\ube44\uc2a4",
            "\uc678\ubd80\uc11c\ube44\uc2a4",
            "\uc11c\ube44\uc2a4",
            "\ube0c\ub9ac\uc9c0",
        ],
    ) and has_any_final(normalized, HEALTH_TOKENS_FINAL)


def is_echo_request_final(text):
    """Return whether text asks system.echo to send/echo a message."""
    normalized = normalize_final(text)

    if has_any_final(normalized, SYSTEM_ECHO_ALIASES_FINAL):
        return True

    return has_any_final(normalized, INTEGRATION_SUBJECTS_FINAL) and has_any_final(normalized, SEND_TOKENS_FINAL)


def cleanup_echo_message_final(text):
    """Remove workflow command words and leave only the message payload."""
    value = str(text or "").strip()
    value = strip_prefix_aliases_final(value, N8N_ALIASES_FINAL)
    value = strip_prefix_aliases_final(value, SYSTEM_ECHO_ALIASES_FINAL)
    value = _re.sub(r"^\s*(\uc790\ub3d9\ud654|\uc678\ubd80\s*\uc790\ub3d9\ud654|workflow|\uc6cc\ud06c\ud50c\ub85c\uc6b0)\s*(\ub85c|\uc73c\ub85c)?\s*", "", value, flags=_re.IGNORECASE)
    value = _re.sub(r"\s*(\ubcf4\ub0b4\s*\uc918|\ubcf4\ub0b4\uc918|\ubcf4\uc5ec\s*\uc918|\ubcf4\uc5ec\uc918|\uc804\uc1a1\ud574\s*\uc918|\uc804\uc1a1\ud574\uc918|\uc2e4\ud589\ud574\s*\uc918|\uc2e4\ud589\ud574\uc918)\s*$", "", value)
    value = value.strip()

    if len(value) > 1 and value[-1] in ("\uc744", "\ub97c"):
        value = value[:-1].strip()

    return value


def strip_prefix_aliases_final(text, aliases):
    """Strip one command alias from the start of text."""
    value = str(text or "").strip()

    for alias in sorted(aliases, key=len, reverse=True):
        pattern = _re.compile(rf"^\s*{_re.escape(alias)}\s*(\uc740|\ub294|\uc73c\ub85c|\ub85c)?\s*", _re.IGNORECASE)
        value = pattern.sub("", value)

    return value.strip()


def is_notification_test_request_final(text):
    """Return whether text asks for the built-in notification test workflow."""
    return has_any_final(text, NOTIFICATION_TEST_ALIASES_FINAL)


def is_integration_workflow_request(text):
    """Return whether text is an integration request even before a workflow is known."""
    normalized = normalize_final(text)

    if is_system_health_alias_final(normalized) or is_echo_request_final(normalized) or is_notification_test_request_final(normalized):
        return True

    return has_any_final(normalized, INTEGRATION_SUBJECTS_FINAL) and has_any_final(
        normalized,
        WORKFLOW_TOKENS_FINAL + EXECUTE_TOKENS_FINAL + SEND_TOKENS_FINAL,
    )
