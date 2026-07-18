import inspect
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from jarvis.result_merge import UnifiedResult
from jarvis.voice import MockVoiceProvider, VoiceProvider, VoiceResult, VoiceService
from jarvis.voice import service as voice_service_module
from jarvis.voice.providers import base as voice_provider_base
from jarvis.voice.providers import mock as mock_provider_module
from jarvis.voice.providers import openai as openai_provider_module
from jarvis.voice.user_vocabulary import format_corrections, normalize_stt_text


class TestVoiceIntegration(unittest.TestCase):
    """Test v0.4 Beta.5 Voice Integration."""

    def test_voice_service_reads_unified_result_summary_only(self):
        """Check VoiceService sends only UnifiedResult.summary to provider."""
        provider = RecordingVoiceProvider()
        response = UnifiedResult(
            summary="오늘 일정은 15시 회의입니다.",
            results=(
                {
                    "capability": "calendar",
                    "result": "Meeting 15:00",
                },
            ),
            warnings=(
                {
                    "message": "Rain likely",
                },
            ),
            errors=(
                {
                    "message": "Calendar detail should not be spoken",
                },
            ),
            metadata={
                "execution_id": "exec_voice",
            },
        )

        result = VoiceService(provider=provider).speak(response)

        self.assertEqual(provider.seen_text, "오늘 일정은 15시 회의입니다.")
        self.assertEqual(result.text, "오늘 일정은 15시 회의입니다.")
        self.assertNotIn("Meeting 15:00", result.text)
        self.assertNotIn("Rain likely", result.text)
        self.assertNotIn("exec_voice", result.text)

    def test_mock_voice_provider_returns_same_text_without_audio(self):
        """Check MockVoiceProvider creates VoiceResult without real audio."""
        result = MockVoiceProvider().synthesize("오늘 일정은 15시 회의입니다.")

        self.assertIsInstance(result, VoiceResult)
        self.assertEqual(result.text, "오늘 일정은 15시 회의입니다.")
        self.assertIsNone(result.audio)
        self.assertEqual(result.provider, "mock")
        self.assertFalse(result.metadata["audio_generated"])
        self.assertFalse(result.metadata["playback_ready"])

    def test_voice_provider_can_be_replaced_by_dependency_injection(self):
        """Check VoiceService works the same with a different provider."""
        provider = DummyVoiceProvider()
        response = UnifiedResult(summary="테스트 응답")

        result = VoiceService(provider=provider).speak(response)

        self.assertEqual(result.text, "dummy: 테스트 응답")
        self.assertEqual(result.provider, "dummy")
        self.assertEqual(result.audio, b"audio")
        self.assertTrue(isinstance(provider, VoiceProvider))

    def test_voice_result_is_immutable(self):
        """Check VoiceResult is immutable after provider synthesis."""
        result = MockVoiceProvider().synthesize("hello")

        with self.assertRaises(FrozenInstanceError):
            result.text = "changed"

        with self.assertRaises(TypeError):
            result.metadata["audio_generated"] = True

    def test_voice_layer_does_not_import_forbidden_orchestration_layers(self):
        """Check Voice depends on UnifiedResult shape, not orchestration internals."""
        source = "\n".join(
            inspect.getsource(module)
            for module in [
                voice_service_module,
                voice_provider_base,
                mock_provider_module,
                openai_provider_module,
            ]
        )

        forbidden = [
            "jarvis.planner",
            "IntentPlanner",
            "jarvis.execution",
            "ExecutionGraph",
            "ExecutionGraphRunner",
            "jarvis.capabilities",
            "Capability",
        ]

        for value in forbidden:
            self.assertNotIn(value, source)

    def test_openai_voice_provider_placeholder_exists(self):
        """Check OpenAI voice provider file exists as a reserved provider hook."""
        self.assertTrue(hasattr(openai_provider_module, "OpenAIVoiceProvider"))

    def test_legacy_voice_providers_file_was_replaced_by_package(self):
        """Check provider package migration does not leave an ambiguous module file."""
        self.assertFalse((Path("jarvis") / "voice" / "providers.py").exists())

    def test_stt_user_vocabulary_corrects_proper_name_aliases(self):
        """Check STT aliases are canonicalized before intent parsing."""
        result = normalize_stt_text(" 아이와   처음 만난 날은 2026년 3월 26일이야. 기억해. ")

        self.assertEqual(result.normalized_text, "아야 처음 만난 날은 2026년 3월 26일이야. 기억해.")
        self.assertEqual(format_corrections(result.corrections), ["아이와->아야"])

    def test_stt_user_vocabulary_uses_longest_alias_first(self):
        """Check particle aliases become canonical names without partial replacement."""
        result = normalize_stt_text("아야랑 처음 만난 게 언제였지?")

        self.assertEqual(result.normalized_text, "아야 처음 만난 게 언제였지?")
        self.assertEqual(format_corrections(result.corrections), ["아야랑->아야"])

    def test_stt_user_vocabulary_corrects_aya_openai_aliases(self):
        """Check OpenAI STT proper-name variants are canonicalized."""
        result = normalize_stt_text("아연와 만나기 일정 등록해")

        self.assertEqual(result.normalized_text, "아야 만나기 일정 등록해")
        self.assertEqual(format_corrections(result.corrections), ["아연와->아야"])


    def test_stt_user_vocabulary_corrects_n8n_aliases(self):
        """Check common Korean STT mistakes for n8n are corrected."""
        result = normalize_stt_text("맨발은 연결 상태 확인해 줘")

        self.assertEqual(result.normalized_text, "n8n 연결 상태 확인해 줘")
        self.assertEqual(format_corrections(result.corrections), ["맨발은->n8n"])

    def test_stt_user_vocabulary_corrects_nam_alias(self):
        """Check English-looking n8n STT mistakes are corrected."""
        result = normalize_stt_text("nam 연결 상태 확인해 줘")

        self.assertEqual(result.normalized_text, "n8n 연결 상태 확인해 줘")
        self.assertEqual(format_corrections(result.corrections), ["nam->n8n"])

    def test_stt_user_vocabulary_corrects_nan_and_n8_aliases(self):
        """Check additional n8n STT mistakes are corrected."""
        nan_result = normalize_stt_text("nan 자동화로 안녕하세요를 보내 줘")
        n8_result = normalize_stt_text("n8 workflow 실행해 줘")

        self.assertEqual(nan_result.normalized_text, "n8n 자동화로 안녕하세요를 보내 줘")
        self.assertEqual(format_corrections(nan_result.corrections), ["nan->n8n"])
        self.assertEqual(n8_result.normalized_text, "n8n workflow 실행해 줘")
        self.assertEqual(format_corrections(n8_result.corrections), ["n8->n8n"])

    def test_stt_user_vocabulary_corrects_workflow_aliases(self):
        """Check English STT splits for workflow are corrected."""
        walk_result = normalize_stt_text("nan walk flo 실행해 줘")
        work_result = normalize_stt_text("nan work flo 실행해 줘")

        self.assertEqual(walk_result.normalized_text, "n8n workflow 실행해 줘")
        self.assertEqual(format_corrections(walk_result.corrections), ["nan->n8n", "walk flo->workflow"])
        self.assertEqual(work_result.normalized_text, "n8n workflow 실행해 줘")
        self.assertEqual(format_corrections(work_result.corrections), ["nan->n8n", "work flo->workflow"])


    def test_stt_user_vocabulary_corrects_system_echo_aliases(self):
        """Check Korean system.echo voice aliases are corrected."""
        joined = normalize_stt_text("\uc2dc\uc2a4\ud15c\uc5d0\ucf54 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        dotted = normalize_stt_text("\uc2dc\uc2a4\ud15c\uc9ec\uc5d0\ucf54 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        macpo = normalize_stt_text("\uc2dc\uc2a4\ud15c \ub9e5\ud3ec \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        hago = normalize_stt_text("\uc2dc\uc2a4\ud15c \ud558\uace0 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        four = normalize_stt_text("\uc2dc\uc2a4\ud15c4 \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")

        self.assertEqual(joined.normalized_text, "system.echo \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        self.assertEqual(format_corrections(joined.corrections), ["\uc2dc\uc2a4\ud15c\uc5d0\ucf54->system.echo"])
        self.assertEqual(dotted.normalized_text, "system.echo \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        self.assertEqual(format_corrections(dotted.corrections), ["\uc2dc\uc2a4\ud15c\uc9ec\uc5d0\ucf54->system.echo"])
        self.assertEqual(macpo.normalized_text, "system.echo \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        self.assertEqual(hago.normalized_text, "system.echo \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")
        self.assertEqual(four.normalized_text, "system.echo \uc548\ub155\ud558\uc138\uc694 \ubcf4\ub0b4 \uc918")

    def test_stt_user_vocabulary_corrects_n8n_currency_alias(self):
        """Check Korean currency-looking n8n mistake is corrected."""
        result = normalize_stt_text("\uc5d4\ud654\ub97c \uc0c1\ud0dc \ud655\uc778\ud574 \uc918")

        self.assertEqual(result.normalized_text, "n8n \uc0c1\ud0dc \ud655\uc778\ud574 \uc918")
        self.assertEqual(format_corrections(result.corrections), ["\uc5d4\ud654\ub97c->n8n"])

    def test_stt_user_vocabulary_corrects_seoul_station_alias(self):
        """Check common Seoul Station STT mistakes are corrected."""
        result = normalize_stt_text("\uadf8 \uc77c\uc815 \uc124\ub9bd\uc73c\ub85c \ubc14\uafd4")

        self.assertEqual(result.normalized_text, "\uadf8 \uc77c\uc815 \uc11c\uc6b8\uc5ed\uc73c\ub85c \ubc14\uafd4")
        self.assertEqual(format_corrections(result.corrections), ["\uc124\ub9bd->\uc11c\uc6b8\uc5ed"])


class RecordingVoiceProvider:
    """Provider stub that records text passed by VoiceService."""

    def __init__(self):
        """Create a recording provider."""
        self.seen_text = None

    def synthesize(self, text):
        """Record text and return it as a voice result."""
        self.seen_text = text
        return VoiceResult(
            text=text,
            audio=None,
            provider="recording",
            duration_ms=1,
            metadata={},
        )


class DummyVoiceProvider:
    """Provider stub used to prove DI."""

    def synthesize(self, text):
        """Return deterministic dummy audio."""
        return VoiceResult(
            text=f"dummy: {text}",
            audio=b"audio",
            provider="dummy",
            duration_ms=2,
            metadata={
                "audio_generated": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
