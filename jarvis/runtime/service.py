"""Shared Jarvis Runtime Service for CLI, local voice, and web clients."""

import base64
from pathlib import Path
from threading import RLock, Timer
from uuid import uuid4

from jarvis.debug_trace import trace_event
from jarvis.input import InputManager, InputModality, InputSource
from jarvis.runtime.turn_lock import (
    BusyPolicy,
    RuntimeTurnInterrupted,
    RuntimeTurnLock,
    TurnOwner,
    TurnPriority,
)
from jarvis.runtime.language import LanguagePolicy, LanguageResolver
from jarvis.voice.providers import transcribe_stt_audio
from jarvis.voice.session import create_voice_session


class JarvisRuntimeService:
    """Normalize interactive input and execute it through one VoicePipeline."""

    def __init__(
        self,
        pipeline,
        config,
        input_manager=None,
        wake_manager=None,
        playback_timeout=120,
        turn_lock=None,
    ):
        self.pipeline = pipeline
        self.config = config
        self.input_manager = input_manager or InputManager()
        self._lock = RLock()
        self._state_lock = RLock()
        self.pipeline.interaction_lock = self._lock
        self.wake_manager = wake_manager
        self.turn_lock = turn_lock or RuntimeTurnLock(
            on_acquired=self._on_turn_acquired,
            on_released=self._on_turn_released,
        )
        self.pipeline.runtime_turn_lock = self.turn_lock
        language = getattr(config, "language", None)
        self.pipeline.language_resolver = LanguageResolver(
            policy=getattr(language, "policy", LanguagePolicy.AUTO),
            voices={
                "ko": getattr(language, "ko_voice", "openai:alloy:ko"),
                "ja": getattr(language, "ja_voice", "openai:nova:ja"),
                "en": getattr(language, "en_voice", "openai:onyx:en"),
            },
        )
        if (
            str(getattr(language, "policy", "AUTO")).upper() == "AUTO"
            and getattr(self.pipeline, "stt_provider", None) is not None
            and self.pipeline.stt_provider.__class__.__name__.startswith("OpenAI")
        ):
            self.pipeline.stt_provider.language = "auto"
        conversation = getattr(config, "conversation", None)
        self.dashboard_session = create_voice_session(
            max_turns=getattr(conversation, "max_turns", 6),
            max_tokens=getattr(conversation, "max_tokens", 1200),
        )
        self.dashboard_conversation_session = None
        self.playback_timeout = max(5, int(playback_timeout))
        self._playback_tokens = {}

    @property
    def session_id(self):
        return str(self.dashboard_session.session_id)

    def submit_text(self, text, source=InputSource.KEYBOARD, _playback_token=""):
        normalized = str(text or "").strip()
        if normalized == "":
            raise ValueError("Input text is empty.")
        playback_token = _playback_token or self._begin_dashboard_turn()
        envelope = self.input_manager.create(
            source=source,
            modality=InputModality.TEXT,
            content=normalized,
            correlation_id=self.session_id,
            metadata={"stage": "web", "client": "dashboard"},
        )
        trace_event(
            "runtime.input.received",
            input_id=envelope.input_id,
            source=envelope.source.value,
            modality=envelope.modality.value,
            session_id=self.session_id,
            content_length=len(normalized),
        )
        try:
            with self._lock:
                turn = self._playback_tokens[playback_token]["turn_token"]
                reply, audio = self._process_dashboard_text(envelope, normalized, turn)
        except Exception:
            self.finish_browser_playback(playback_token, reason="interaction_failed")
            raise
        trace_event(
            "runtime.output.completed",
            input_id=envelope.input_id,
            source=envelope.source.value,
            response_length=len(str(reply or "")),
            has_audio=bool(audio),
        )
        return {
            "input": envelope.to_dict(),
            "text": str(reply or ""),
            "audio": audio,
            "audio_mime": self._audio_mime(),
            "playback_token": playback_token,
            "session_id": self.session_id,
            "language_context": (
                self.pipeline.language_context.to_dict()
                if getattr(self.pipeline, "language_context", None) is not None
                else {}
            ),
        }

    def submit_audio(self, audio, mime_type="audio/webm"):
        if not isinstance(audio, (bytes, bytearray)) or len(audio) == 0:
            raise ValueError("Audio input is empty.")
        playback_token = self._begin_dashboard_turn()
        envelope = self.input_manager.create(
            source=InputSource.VOICE,
            modality=InputModality.AUDIO,
            content=bytes(audio),
            correlation_id=self.session_id,
            metadata={"stage": "browser_stt", "mime_type": mime_type, "client": "dashboard"},
        )
        trace_event(
            "runtime.input.received",
            input_id=envelope.input_id,
            source="voice",
            modality="audio",
            session_id=self.session_id,
            content_length=len(audio),
        )
        suffix = ".webm" if "webm" in mime_type else ".wav"
        try:
            language_policy = getattr(
                getattr(self.config, "language", None),
                "policy",
                "AUTO",
            )
            stt_language = (
                "auto"
                if str(language_policy).upper() == "AUTO"
                else self.config.stt.openai_language
            )
            text = transcribe_stt_audio(
                bytes(audio),
                model=self.config.stt.openai_model,
                language=stt_language,
                provider="browser_openai",
                reason="dashboard_push_to_talk",
                audio_suffix=suffix,
            )
            if not str(text or "").strip():
                raise ValueError("Speech was not recognized.")
            result = self.submit_text(
                text,
                source=InputSource.VOICE,
                _playback_token=playback_token,
            )
        except Exception:
            self.finish_browser_playback(playback_token, reason="stt_failed")
            raise
        result["transcript"] = text
        result["input"] = envelope.to_dict()
        return result

    def finish_browser_playback(self, playback_token, reason="browser_ack"):
        token = str(playback_token or "")
        with self._state_lock:
            pending = self._playback_tokens.pop(token, None)
        if pending is None:
            return False
        pending["timer"].cancel()
        self.turn_lock.release(pending["turn_token"], reason=reason)
        trace_event(
            "runtime.state.changed",
            state="VOICE_IDLE",
            source="dashboard",
            reason=reason,
        )
        return True

    def _begin_dashboard_turn(self):
        turn_token = self.turn_lock.acquire(
            TurnOwner.DASHBOARD,
            policy=BusyPolicy.REJECT,
            soft_timeout=self.playback_timeout / 2,
            hard_timeout=self.playback_timeout,
            priority=TurnPriority.USER,
            source="browser",
            conversation_id=self.session_id,
        )
        token = f"PB-{uuid4().hex[:10].upper()}"
        timer = Timer(
            self.playback_timeout,
            lambda: self.finish_browser_playback(token, reason="playback_timeout"),
        )
        timer.daemon = True
        with self._state_lock:
            self._playback_tokens[token] = {
                "timer": timer,
                "turn_token": turn_token,
            }
        timer.start()
        trace_event(
            "runtime.state.changed",
            state="DASHBOARD_CHAT",
            source="dashboard",
            session_id=self.session_id,
        )
        return token

    def _on_turn_acquired(self, token):
        if self.wake_manager is not None:
            self.wake_manager.pause(f"runtime_owner:{token.owner.value}")

    def _on_turn_released(self, token, reason):
        del token
        if self.wake_manager is not None:
            self.wake_manager.resume(str(reason or "turn_released"))

    def _process_dashboard_text(self, envelope, normalized, turn):
        original_voice_session = getattr(self.pipeline, "voice_session", None)
        original_conversation = getattr(self.pipeline, "conversation_session", None)
        chat_service = getattr(self.pipeline, "chat_service", None)
        original_chat_session = getattr(chat_service, "voice_session", None)
        intent_runtime = getattr(self.pipeline, "intent_runtime", None)
        tool_dispatcher = getattr(intent_runtime, "tool_dispatcher", None)
        memory_manager = getattr(tool_dispatcher, "memory_manager", None)
        original_memory_session_id = getattr(memory_manager, "session_id", None)
        try:
            self.pipeline.voice_session = self.dashboard_session
            if chat_service is not None:
                chat_service.voice_session = self.dashboard_session
            if memory_manager is not None and hasattr(memory_manager, "session_id"):
                memory_manager.session_id = self.session_id
            self.pipeline.conversation_session = self.dashboard_conversation_session
            if self.pipeline.conversation_session is None:
                self.pipeline.start_conversation_session()
            self.pipeline.last_input_envelope = envelope
            reply = self.pipeline.process_follow_up_text(normalized, speak=False)
            turn.language_context = getattr(self.pipeline, "language_context", None)
            runtime_task = getattr(self.pipeline.conversation_session, "runtime_task", None)
            if runtime_task is not None:
                self.turn_lock.link_task(turn, getattr(runtime_task, "id", ""))
            if self.turn_lock.cancellation_requested(turn):
                raise RuntimeTurnInterrupted("Dashboard turn was preempted.")
            self.dashboard_conversation_session = self.pipeline.conversation_session
            audio = self._generate_browser_audio(reply)
            trace_event(
                "runtime.state.changed",
                state="DASHBOARD_TTS",
                source="dashboard",
                session_id=self.session_id,
            )
            return reply, audio
        finally:
            self.pipeline.voice_session = original_voice_session
            self.pipeline.conversation_session = original_conversation
            if chat_service is not None:
                chat_service.voice_session = original_chat_session
            if memory_manager is not None and hasattr(memory_manager, "session_id"):
                memory_manager.session_id = original_memory_session_id

    def _generate_browser_audio(self, text):
        provider = getattr(self.pipeline, "tts_provider", None)
        if not text or provider is None or not hasattr(provider, "generate_audio"):
            return ""
        original_voice = getattr(provider, "voice", None)
        selected_voice = (
            self.pipeline.selected_tts_voice()
            if hasattr(self.pipeline, "selected_tts_voice")
            else ""
        )
        if original_voice is not None and selected_voice:
            provider.voice = selected_voice
        try:
            audio_path = provider.generate_audio(str(text))
        finally:
            if original_voice is not None:
                provider.voice = original_voice
        try:
            return base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def _audio_mime(self):
        response_format = str(getattr(self.config.tts, "response_format", "wav") or "wav")
        return {
            "mp3": "audio/mpeg",
            "opus": "audio/ogg",
            "aac": "audio/aac",
            "flac": "audio/flac",
        }.get(response_format, "audio/wav")
