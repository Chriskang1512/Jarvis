import logging
import re
import unicodedata
from datetime import date, datetime, timedelta
from time import perf_counter

from jarvis.date_calculator import elapsed_days_since, format_korean_date, is_iso_date, today
from jarvis.brain.intent_runtime import RuntimeResult
from jarvis.debug_trace import trace_event
from jarvis.runtime.planner import PlanStepResult
from jarvis.runtime.task import RuntimeTask, TaskState, TaskStepRecord
from jarvis.runtime.conversation_task import (
    CALENDAR_TASK_ACTIVE,
    CALENDAR_TASK_CANCELLED,
    CALENDAR_TASK_COMPLETED,
    CALENDAR_TASK_EXPIRED,
    EXECUTE_CALENDAR_TASK,
    FIELD_DATE,
    FIELD_LOCATION,
    FIELD_PARTICIPANTS,
    FIELD_TIME,
    FIELD_TITLE,
    build_calendar_input,
    calendar_conversation_reminder_minutes,
    extract_calendar_fields,
    question_for_field,
    should_start_calendar_conversation,
    start_calendar_conversation_task,
    update_calendar_conversation_task,
)
from jarvis.tools import ToolRequest
from jarvis.voice.conversation import CONVERSATION_FOLLOW_UP, CONVERSATION_IDLE
from jarvis.voice.conversation import CONVERSATION_LISTENING, CONVERSATION_SPEAKING
from jarvis.voice.conversation import CONVERSATION_THINKING, create_conversation_session
from jarvis.voice.semantic import SemanticTranscriptContext, SemanticTranscriptNormalizer
from jarvis.voice.text_normalizer import normalize_tts_text
from jarvis.voice.user_vocabulary import format_corrections, normalize_stt_text


class VoicePipeline:
    """Run the wake word, STT, LLM, and TTS pipeline."""

    def __init__(
        self,
        wake_listener,
        stt_provider,
        chat_service,
        tts_provider,
        logger=None,
        diagnostics_collector=None,
        voice_session=None,
        intent_runtime=None,
        runtime_console=None,
        follow_up_timeout=0.0,
        conversation_session=None,
        semantic_normalizer=None,
    ):
        """Create a voice pipeline with replaceable modules."""
        self.wake_listener = wake_listener
        self.stt_provider = stt_provider
        self.chat_service = chat_service
        self.tts_provider = tts_provider
        self.logger = logger or logging.getLogger("jarvis.voice")
        self.diagnostics_collector = diagnostics_collector
        self.voice_session = voice_session
        self.intent_runtime = intent_runtime
        self.runtime_console = runtime_console
        self.follow_up_timeout = float(follow_up_timeout)
        self.conversation_session = conversation_session
        self.semantic_normalizer = semantic_normalizer or SemanticTranscriptNormalizer()
        self.runtime_last_calendar_result = None
        self.runtime_last_calendar_event = None

    def run_once(self):
        """Run one complete voice conversation turn."""
        if self.voice_session is not None:
            self.voice_session.start_turn()

        self.logger.info("wake_word.waiting")
        self.set_session_stage("wake")
        self.publish_pipeline(wake="waiting", current_stage="wake")
        self.log_event("Wake waiting")
        self.wake_listener.wait_for_wake_word()
        self.logger.info("wake_word.detected")
        self.publish_pipeline(wake="detected", current_stage="stt")
        self.log_event("Wake detected")
        self.start_conversation_session()
        first_reply = self.process_voice_turn()
        self.run_follow_up_loop()
        return first_reply

    def process_voice_turn(self):
        """Process one voice turn without requiring a wake word."""
        total_start = perf_counter()
        stt_latency = 0.0
        llm_latency = 0.0
        tts_latency = 0.0

        self.logger.info("stt.started")
        self.set_session_stage("stt")
        self.set_conversation_state(CONVERSATION_LISTENING)
        stt_start = perf_counter()
        self.publish_pipeline(stt="started", current_stage="stt")
        self.log_event("STT started")
        user_message = self.listen_and_normalize_stt()
        stt_latency = perf_counter() - stt_start
        trace_event(
            "voice.stt.completed",
            stt_success=not should_skip_voice_message(user_message),
            recognized_text=user_message,
        )
        self.logger.info("stt.finished")
        self.publish_pipeline(stt="finished", current_stage="llm")
        self.log_event("STT finished")

        if should_skip_voice_message(user_message):
            self.logger.info("stt.empty")
            trace_event(
                "voice.stt.skipped",
                stt_success=False,
                recognized_text=user_message,
            )
            self.publish_pipeline(stt="empty", current_stage="idle")
            self.publish_performance(llm_latency, perf_counter() - total_start, stt_latency, tts_latency)
            self.log_event("STT returned empty or failed input")
            return ""

        self.set_conversation_state(CONVERSATION_THINKING)
        intent_result = None
        reply = self.try_calendar_conversation_task_reply(user_message)

        if reply is None:
            reply = self.try_pending_action_confirmation_reply(user_message)

        if reply is None:
            reply = self.try_pending_clarification_reply(user_message)

        if reply is None:
            reply = self.try_calendar_update_reply(user_message)

        if reply is None:
            reply = self.try_memory_date_elapsed_reply(user_message)

        fallback = ""

        if reply is not None:
            self.publish_pipeline(llm="skipped", current_stage="tts")
        else:
            intent_result = self.try_intent_runtime(user_message)

        if reply is None and intent_result is not None and intent_result.handled:
            reply = intent_result.response
            self.remember_pending_action(intent_result)
            self.remember_pending_clarification(intent_result, user_message)
            self.remember_recalled_memory(intent_result)
            self.remember_calendar_result(intent_result)
            self.remember_reminder_result(intent_result)
            self.remember_runtime_task(intent_result)
            trace_event(
                "voice.intent.handled",
                routed_ability=getattr(intent_result, "tool", ""),
                ability_result_success=getattr(intent_result, "success", False),
            )
            self.publish_pipeline(llm="skipped", current_stage="tts")
        elif reply is None:
            if is_alarm_like_request(user_message):
                reply = "알림 시간을 다시 말씀해 주세요."
                self.publish_pipeline(llm="skipped", current_stage="tts")
            elif is_todo_like_failed_request(user_message):
                reply = "할 일 내용과 추가할지를 다시 말씀해 주세요."
                self.publish_pipeline(llm="skipped", current_stage="tts")
            else:
                fallback = self.get_fallback_name()
                self.logger.info("llm.started")
                self.set_session_stage("llm")
                llm_start = perf_counter()
                self.publish_pipeline(llm="started", current_stage="llm")
                self.log_event("LLM started")
                reply = self.chat_service.generate_reply(user_message)
                llm_latency = perf_counter() - llm_start
                self.logger.info("llm.finished")
                self.publish_pipeline(llm="finished", current_stage="tts")
                self.publish_provider_metadata()
                self.log_event("LLM finished")

        self.logger.info("tts.started")
        self.set_session_stage("tts")
        self.set_conversation_state(CONVERSATION_SPEAKING)
        tts_start = perf_counter()
        self.publish_pipeline(tts="started", current_stage="tts")
        self.log_event("voice.tts.started")
        self.print_llm_response_debug(reply)
        trace_event("voice.tts.final_text", final_tts_text=reply)
        self.speak_reply(reply)
        self.publish_intent_tts_output(intent_result)
        tts_latency = perf_counter() - tts_start
        self.logger.info("tts.playback.finished")
        self.set_session_stage("idle")
        self.publish_pipeline(tts="finished", current_stage="idle")
        self.publish_performance(llm_latency, perf_counter() - total_start, stt_latency, tts_latency)
        self.log_event("voice.tts.playback.completed")
        self.print_runtime_console(
            intent_result,
            fallback=fallback,
            response=reply,
            provider=self.get_provider_name(),
            conversation=self.conversation_session,
        )

        return reply

    def run_follow_up_loop(self):
        """Listen for follow-up turns until the session timeout expires."""
        if self.conversation_session is None:
            return

        if self.follow_up_timeout <= 0:
            self.close_conversation_session()
            return

        while True:
            self.enter_follow_up_state()
            follow_up_text = self.listen_for_follow_up()

            if should_skip_voice_message(follow_up_text):
                if self.has_calendar_conversation_task():
                    self.speak_calendar_conversation_retry()
                    continue

                if self.has_pending_action():
                    self.speak_pending_action_retry()
                    if str(follow_up_text or "").strip() == "":
                        self.advance_pending_action_turn()
                    if not self.has_pending_action():
                        self.close_conversation_session()
                        return
                    continue

                self.close_conversation_session()
                return

            self.process_follow_up_text(follow_up_text)

    def process_follow_up_text(self, user_message):
        """Process one follow-up text without wake-word detection."""
        total_start = perf_counter()
        llm_latency = 0.0
        tts_latency = 0.0
        self.set_conversation_state(CONVERSATION_THINKING)
        fallback = ""
        intent_result = None
        reply = self.try_calendar_conversation_task_reply(user_message)

        if reply is None:
            reply = self.try_pending_action_confirmation_reply(user_message)

        if reply is None:
            reply = self.try_pending_clarification_reply(user_message)

        if reply is None:
            reply = self.try_calendar_reminder_follow_up_reply(user_message)

        if (
            reply is None
            and not is_todo_ordinal_or_mutation_text(user_message)
            and not is_calendar_query_command_text(user_message)
        ):
            reply = self.try_calendar_follow_up_reply(user_message)

        if reply is None:
            reply = self.try_calendar_update_reply(user_message)

        if reply is None:
            reply = self.try_memory_date_elapsed_reply(user_message)
        memory_context_refreshed = False

        if reply is not None:
            self.publish_pipeline(llm="skipped", current_stage="tts")
        else:
            intent_result = self.try_intent_runtime(user_message)

        if reply is None and intent_result is not None and intent_result.handled:
            reply = intent_result.response
            self.remember_pending_action(intent_result)
            self.remember_pending_clarification(intent_result, user_message)
            memory_context_refreshed = self.remember_recalled_memory(intent_result)
            self.remember_calendar_result(intent_result)
            self.remember_reminder_result(intent_result)
            self.remember_runtime_task(intent_result)
            trace_event(
                "voice.intent.handled",
                routed_ability=getattr(intent_result, "tool", ""),
                ability_result_success=getattr(intent_result, "success", False),
            )
            self.publish_pipeline(llm="skipped", current_stage="tts")
        elif reply is None:
            if is_alarm_like_request(user_message):
                reply = "알림 시간을 다시 말씀해 주세요."
                self.publish_pipeline(llm="skipped", current_stage="tts")
            elif is_todo_like_failed_request(user_message):
                reply = "할 일 내용과 추가할지를 다시 말씀해 주세요."
                self.publish_pipeline(llm="skipped", current_stage="tts")
            else:
                fallback = self.get_fallback_name()
                self.logger.info("llm.started")
                self.set_session_stage("llm")
                llm_start = perf_counter()
                self.publish_pipeline(llm="started", current_stage="llm")
                self.log_event("LLM started")
                reply = self.chat_service.generate_reply(user_message)
                llm_latency = perf_counter() - llm_start
                self.logger.info("llm.finished")
                self.publish_pipeline(llm="finished", current_stage="tts")
                self.publish_provider_metadata()
                self.log_event("LLM finished")

        self.logger.info("tts.started")
        self.set_session_stage("tts")
        self.set_conversation_state(CONVERSATION_SPEAKING)
        tts_start = perf_counter()
        self.publish_pipeline(tts="started", current_stage="tts")
        self.log_event("voice.tts.started")
        self.print_llm_response_debug(reply)
        trace_event("voice.tts.final_text", final_tts_text=reply)
        self.speak_reply(reply)
        self.publish_intent_tts_output(intent_result)
        tts_latency = perf_counter() - tts_start
        self.logger.info("tts.playback.finished")
        self.publish_pipeline(tts="finished", current_stage="follow_up")
        self.publish_performance(llm_latency, perf_counter() - total_start, 0.0, tts_latency)
        self.log_event("voice.tts.playback.completed")
        self.print_runtime_console(
            intent_result,
            fallback=fallback,
            response=reply,
            provider=self.get_provider_name(),
            conversation=self.conversation_session,
        )

        if not memory_context_refreshed:
            self.advance_last_memory_result_turn()

    def try_calendar_conversation_task_reply(self, user_message):
        """Continue or start a Calendar-only conversation task."""
        if self.conversation_session is None:
            return None

        task = self.conversation_session.get_conversation_task()

        if task is not None and getattr(task, "task_state", "") == CALENDAR_TASK_ACTIVE:
            reply = update_calendar_conversation_task(task, user_message)

            if reply == EXECUTE_CALENDAR_TASK:
                return self.execute_calendar_conversation_task(task)

            if getattr(task, "task_state", "") in [
                CALENDAR_TASK_COMPLETED,
                CALENDAR_TASK_CANCELLED,
                CALENDAR_TASK_EXPIRED,
            ]:
                self.conversation_session.clear_conversation_task()

            return reply

        if task is not None and getattr(task, "task_state", "") == CALENDAR_TASK_EXPIRED:
            return "일정 등록 작업이 만료되었습니다. 다시 말씀해 주세요."

        if should_start_calendar_conversation(user_message):
            task = start_calendar_conversation_task(user_message)
            self.conversation_session.set_conversation_task(task)
            return question_for_field(getattr(task, "pending_clarification", ""))

        return None

    def execute_calendar_conversation_task(self, task):
        """Execute a collected Calendar conversation task."""
        if self.intent_runtime is None:
            return "실행할 수 있는 런타임이 없습니다."

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None or not hasattr(dispatcher, "execute"):
            return "실행할 수 있는 디스패처가 없습니다."

        input_data = build_calendar_input(task, confirmed=True)
        started = perf_counter()
        trace_event("task.started", task_id=task.id, goal=getattr(task, "raw_text", ""), step_count=1)
        trace_event("task.step_started", task_id=task.id, step_index=1, step_count=1, tool_name="calendar", action="create")
        result = dispatcher.execute(ToolRequest(tool_name="calendar", input_data=input_data), task_id=task.id)
        duration_ms = int((perf_counter() - started) * 1000)
        output = getattr(result, "output", None)

        if not getattr(result, "success", False):
            data = getattr(output, "data", None)

            if hasattr(data, "to_natural_language"):
                return data.to_natural_language()

            return getattr(result, "error", "") or "실행에 실패했습니다."

        if not getattr(result, "success", False):
            trace_event(
                "task.step_failed",
                task_id=task.id,
                step_index=1,
                tool_name="calendar",
                attempts=1,
                duration_ms=duration_ms,
                error=getattr(result, "error", ""),
            )
            trace_event("task.completed", task_id=task.id, status="FAILED", step_count=1, retry_count=0, duration_ms=duration_ms)
            trace_event("task.summary", task_id=task.id, status="FAILED", step_count=1, retry_count=0, duration_ms=duration_ms)
            return getattr(result, "error", "일정 등록에 실패했습니다.")

        output = getattr(result, "output", None)
        data = getattr(output, "data", None)
        self.store_calendar_result(data)
        trace_event(
            "task.step_completed",
            task_id=task.id,
            step_index=1,
            tool_name="calendar",
            attempts=1,
            duration_ms=duration_ms,
        )
        task.task_state = CALENDAR_TASK_COMPLETED
        task.state = "COMPLETED"
        trace_event(
            "conversation.task",
            task_id=getattr(task, "id", ""),
            state=getattr(task, "state", ""),
            task_state=getattr(task, "task_state", ""),
            missing="",
            turn=getattr(task, "conversation_turn", 0),
        )
        trace_event("task.completed", task_id=task.id, status="SUCCESS", step_count=1, retry_count=0, duration_ms=duration_ms)
        trace_event("task.summary", task_id=task.id, status="SUCCESS", step_count=1, retry_count=0, duration_ms=duration_ms)
        self.store_calendar_conversation_task_history(dispatcher, task, duration_ms)
        self.conversation_session.clear_conversation_task()
        trace_event("conversation.active_task_cleared", task_id=getattr(task, "id", ""))
        reminder_minutes = calendar_conversation_reminder_minutes(task)

        if is_successful_calendar_create(data) and reminder_minutes is not None:
            return f"일정을 등록했고, {format_reminder_offset(reminder_minutes)} 전 알림도 설정했습니다."

        if hasattr(data, "to_natural_language"):
            return data.to_natural_language()

        return str(data or "일정을 등록했습니다.")

    def store_calendar_conversation_task_history(self, dispatcher, task, duration_ms):
        """Store a lightweight RuntimeTask snapshot for a Conversation Calendar execution."""
        history = getattr(dispatcher, "task_history", None)

        if history is None or not hasattr(history, "add"):
            return

        record = TaskStepRecord(
            step_index=1,
            tool_name="calendar",
            action="create",
            status=TaskState.SUCCESS,
            attempts=1,
            duration_ms=int(duration_ms),
        )
        history.add(
            RuntimeTask(
                id=getattr(task, "id", ""),
                goal=getattr(task, "raw_text", ""),
                status=TaskState.SUCCESS,
                completed_steps=(1,),
                step_records=(record,),
                duration_ms=int(duration_ms),
            )
        )

    def try_intent_runtime(self, user_message):
        """Run the v0.5 intent runtime when one is connected."""
        if self.intent_runtime is None:
            return None

        self.set_session_stage("intent")
        self.publish_pipeline(llm="intent", current_stage="intent")
        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is not None and hasattr(dispatcher, "create_plan"):
            plan = dispatcher.create_plan(user_message)

            if getattr(plan, "requires_clarification", False) or getattr(plan, "intent_error", ""):
                trace_event(
                    "voice.clarification.required",
                    question=getattr(plan, "clarification_question", ""),
                    error=getattr(plan, "intent_error", ""),
                )
                return runtime_result_from_plan_result(dispatcher.execute_plan(plan), plan)

            if getattr(plan, "unsupported_reason", "") == "unsupported_conditional":
                return RuntimeResult(
                    handled=True,
                    response="아직 조건부 알림은 지원하지 않습니다.",
                    plan=plan,
                    success=False,
                    error="unsupported_conditional",
                    fallback_used=False,
                )

            if len(getattr(plan, "steps", []) or []) > 0 and hasattr(dispatcher, "execute_plan"):
                return runtime_result_from_plan_result(dispatcher.execute_plan(plan), plan)

        if hasattr(self.intent_runtime, "create_context"):
            return self.intent_runtime.run(
                self.intent_runtime.create_context(
                    user_message,
                    input_source="voice",
                    session_id=self.get_session_id(),
                )
            )

        return self.intent_runtime.run(user_message, input_source="voice")

    def speak_reply(self, reply):
        """Speak a reply using streaming TTS when available."""
        tts_text = normalize_tts_text(reply)
        self.print_tts_input_debug(tts_text)
        streaming_enabled = getattr(self.tts_provider, "streaming_enabled", True)

        if streaming_enabled and hasattr(self.tts_provider, "speak_stream"):
            self.tts_provider.speak_stream(tts_text, session=self.voice_session)
            print(len(tts_text))
            return

        self.tts_provider.speak(tts_text)
        print(len(tts_text))

    def print_llm_response_debug(self, response):
        """Print the response text before it is sent to TTS."""
        text = str(response)
        print(DEBUG_SEPARATOR)
        print("LLM Response")
        print("")
        print(text)
        print("")
        print(f"(전체 길이 : {len(text)} chars)")
        print(DEBUG_SEPARATOR)

    def print_tts_input_debug(self, tts_text):
        """Print the exact text sent into TTS."""
        print(DEBUG_SEPARATOR)
        print("TTS Input")
        print("")
        print(tts_text)
        print("")
        print("Length")
        print("")
        print(len(tts_text))
        print(DEBUG_SEPARATOR)

    def set_session_stage(self, stage):
        """Update the voice session stage when a session exists."""
        if self.voice_session is None:
            return

        self.voice_session.set_stage(stage)

    def publish_pipeline(self, wake=None, stt=None, llm=None, tts=None, current_stage=None):
        """Publish voice pipeline status when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        current_pipeline = self.diagnostics_collector.get_snapshot().pipeline
        self.diagnostics_collector.publish_pipeline(
            wake=choose_status(wake, current_pipeline.wake),
            stt=choose_status(stt, current_pipeline.stt),
            llm=choose_status(llm, current_pipeline.llm),
            tts=choose_status(tts, current_pipeline.tts),
            current_stage=choose_status(current_stage, current_pipeline.current_stage),
        )

    def publish_performance(self, llm_latency, total_latency, stt_latency, tts_latency):
        """Publish voice pipeline timing when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.publish_performance(
            llm_latency=llm_latency,
            total_latency=total_latency,
            stt_latency=stt_latency,
            tts_latency=tts_latency,
        )

    def publish_provider_metadata(self):
        """Publish ChatProvider metadata when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        provider = self.chat_service.provider
        metadata = getattr(provider, "last_metadata", None)

        if metadata is None:
            return

        self.diagnostics_collector.publish_provider(
            provider_name=getattr(metadata, "provider_name", ""),
            model=getattr(metadata, "model", ""),
            finish_reason=getattr(metadata, "finish_reason", ""),
            usage=getattr(metadata, "usage", None),
            created_at=getattr(metadata, "created_at", ""),
        )

    def publish_intent_tts_output(self, intent_result):
        """Publish whether a handled intent reached TTS."""
        if intent_result is None or not intent_result.handled:
            return

        if hasattr(self.intent_runtime, "publish_tts_output"):
            self.intent_runtime.publish_tts_output(True)

    def print_runtime_console(self, intent_result, fallback="", response=None, provider="", conversation=None):
        """Print a readable runtime summary when enabled."""
        if self.runtime_console is None:
            return

        print(
            self.runtime_console.render(
                intent_result,
                fallback=fallback,
                response=response,
                provider=provider,
                conversation=conversation,
            )
        )

    def start_conversation_session(self):
        """Start a wake-word conversation session."""
        self.conversation_session = create_conversation_session(
            follow_up_timeout=self.follow_up_timeout,
        )
        self.conversation_session.start()
        self.seed_conversation_runtime_memory()
        self.publish_conversation_event("conversation.started")

    def seed_conversation_runtime_memory(self):
        """Seed a fresh wake session with recent runtime references."""
        if self.conversation_session is None:
            return

        if self.runtime_last_calendar_result is not None:
            self.conversation_session.set_last_calendar_result(self.runtime_last_calendar_result)

        if self.runtime_last_calendar_event is not None:
            self.conversation_session.set_last_calendar_event(self.runtime_last_calendar_event)

    def enter_follow_up_state(self):
        """Enter follow-up listening state."""
        self.conversation_session.enter_follow_up()
        self.set_session_stage("follow_up")
        self.publish_pipeline(current_stage="follow_up")
        self.publish_conversation_event("conversation.follow_up")

    def close_conversation_session(self):
        """Close the current conversation session and return to idle."""
        if self.conversation_session is None:
            return

        self.conversation_session.close()
        self.set_session_stage("idle")
        self.publish_pipeline(current_stage="idle")
        self.publish_conversation_event("conversation.closed")

    def set_conversation_state(self, state):
        """Set conversation state when a session exists."""
        if self.conversation_session is None:
            return

        self.conversation_session.transition(state)

    def listen_for_follow_up(self):
        """Listen for follow-up speech during the configured timeout."""
        if self.conversation_session is None:
            return ""

        remaining = self.conversation_session.remaining_follow_up_seconds()

        if remaining <= 0:
            return ""

        if self.should_listen_for_confirmation() and hasattr(self.stt_provider, "listen_for_confirmation"):
            return self.listen_and_normalize_stt(remaining=remaining, confirmation=True)

        if hasattr(self.stt_provider, "listen_for_follow_up"):
            return self.listen_and_normalize_stt(remaining=remaining)

        return self.listen_and_normalize_stt()

    def listen_and_normalize_stt(self, remaining=None, confirmation=False):
        """Listen once and apply user vocabulary corrections before routing."""
        self.configure_stt_prompt_context(confirmation=confirmation)

        if confirmation and hasattr(self.stt_provider, "listen_for_confirmation"):
            raw_text = self.stt_provider.listen_for_confirmation(remaining)
        elif remaining is not None and hasattr(self.stt_provider, "listen_for_follow_up"):
            raw_text = self.stt_provider.listen_for_follow_up(remaining)
        else:
            raw_text = self.stt_provider.listen()

        normalization = normalize_stt_text(raw_text)
        trace_event(
            "voice.stt.normalized",
            raw_text=normalization.raw_text,
            normalized_text=normalization.normalized_text,
            corrections=format_corrections(normalization.corrections),
        )
        semantic = self.semantic_normalizer.normalize(
            normalization.raw_text,
            normalization.normalized_text,
            self.create_semantic_transcript_context(),
        )
        return semantic.semantic_text

    def configure_stt_prompt_context(self, confirmation=False):
        """Pass short runtime context to STT providers that support it."""
        if not hasattr(self.stt_provider, "set_prompt_context"):
            return

        self.stt_provider.set_prompt_context(self.create_stt_prompt_context(confirmation=confirmation))

    def create_stt_prompt_context(self, confirmation=False):
        """Return compact context for speech transcription biasing."""
        parts = []

        if confirmation:
            parts.append("confirmation=yes_no")

        pending_action = self.conversation_session.get_pending_action() if self.conversation_session is not None else None

        if pending_action is not None:
            ability = str(pending_action.get("ability", "") or "")
            action = str(pending_action.get("action", "") or "")
            parts.append(f"pending_action={ability}.{action}")
            title = str((pending_action.get("input_data", {}) or {}).get("title", "") or "")

            if title:
                parts.append(f"pending_title={title}")

        task = self.conversation_session.get_conversation_task() if self.conversation_session is not None else None
        pending_field = str(getattr(task, "pending_clarification", "") or "")

        if pending_field:
            parts.append(f"pending_field={pending_field}")

        if self.runtime_last_calendar_event is not None:
            title = str(getattr(self.runtime_last_calendar_event, "title", "") or "")

            if title:
                parts.append(f"last_calendar={title}")

        parts.append("known_people=아야,유이,유리")
        parts.append("known_places=서울역,잠실,롯데월드,강릉 고용보험공단")
        parts.append("todo_words=할 일,할일,우유 사기,약 사기,장보기")
        return "; ".join(parts)

    def create_semantic_transcript_context(self):
        """Build semantic transcript context from the active voice session."""
        task = None

        if self.conversation_session is not None:
            task = self.conversation_session.get_conversation_task()

        pending_field = str(getattr(task, "pending_clarification", "") or "")
        return SemanticTranscriptContext(
            conversation_state=str(getattr(task, "state", "") or ""),
            pending_field=pending_field,
            last_question=question_for_field(pending_field) if pending_field else "",
            last_task_id=str(getattr(task, "id", "") or ""),
            last_calendar_event=self.runtime_last_calendar_event,
            known_people=("아야", "유이", "유리"),
            known_places=("서울역", "롯데월드", "강릉 고용보험공단"),
        )

    def remember_pending_action(self, intent_result):
        """Store confirm-required actions for follow-up confirmation."""
        pending_action = extract_pending_action(intent_result)

        if pending_action is None or self.conversation_session is None:
            return False

        self.conversation_session.set_pending_action(pending_action)
        trace_event(
            "voice.pending_action.saved",
            ability=pending_action.get("ability", ""),
            action=pending_action.get("action", ""),
            expires_turns=self.conversation_session.pending_action_turns_remaining,
        )
        return True

    def remember_pending_clarification(self, intent_result, user_message):
        """Store clarification context for follow-up completion."""
        pending = extract_pending_clarification(intent_result, user_message)

        if pending is None or self.conversation_session is None:
            return False

        self.conversation_session.set_pending_clarification(pending)
        trace_event(
            "voice.pending_clarification.saved",
            kind=pending.get("kind", ""),
            title=pending.get("title", ""),
            expires_turns=self.conversation_session.pending_clarification_turns_remaining,
        )
        return True

    def try_pending_clarification_reply(self, user_message):
        """Complete a pending clarification from a follow-up answer."""
        if self.conversation_session is None:
            return None

        pending = self.conversation_session.get_pending_clarification()

        if pending is None:
            return None

        if pending.get("kind", "") != "reminder_time":
            return None

        minutes = parse_relative_minutes(user_message)

        if minutes is None:
            self.conversation_session.advance_pending_clarification_turn()
            return "몇 분 뒤에 알려드릴까요?"

        self.conversation_session.clear_pending_clarification()
        return self.execute_pending_reminder_clarification(pending, minutes, user_message)

    def execute_pending_reminder_clarification(self, pending, minutes, user_message):
        """Create a reminder after the user supplies the missing delay."""
        if self.intent_runtime is None:
            return "알림을 등록할 수 없습니다."

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None:
            return "알림을 등록할 수 없습니다."

        title = pending.get("title", "") or "알림"
        reminder_time = (datetime.now() + timedelta(minutes=int(minutes))).isoformat(timespec="seconds")
        trace_event(
            "voice.pending_clarification.resolved",
            kind=pending.get("kind", ""),
            title=title,
            minutes=minutes,
        )
        result = dispatcher.execute(
            ToolRequest(
                tool_name="reminder",
                input_data={
                    "action": "create",
                    "title": title,
                    "datetime": reminder_time,
                    "remind_before": 0,
                    "raw_text": user_message,
                },
            )
        )

        if not getattr(result, "success", False):
            return getattr(result, "error", "알림 등록에 실패했습니다.")

        output = getattr(result, "output", None)

        if hasattr(output, "to_natural_language"):
            return output.to_natural_language()

        return str(output)

    def has_pending_action(self):
        """Return whether a confirmation action is pending."""
        return self.conversation_session is not None and self.conversation_session.get_pending_action() is not None

    def has_calendar_conversation_task(self):
        """Return whether a Calendar conversation task is active."""
        if self.conversation_session is None:
            return False

        task = self.conversation_session.get_conversation_task()
        return task is not None and getattr(task, "task_state", "") == CALENDAR_TASK_ACTIVE

    def should_listen_for_confirmation(self):
        """Return whether the next follow-up expects a short yes/no answer."""
        if self.has_pending_action():
            return True

        if self.conversation_session is None:
            return False

        task = self.conversation_session.get_conversation_task()
        return (
            task is not None
            and getattr(task, "task_state", "") == CALENDAR_TASK_ACTIVE
            and getattr(task, "state", "") == "WAIT_CONFIRMATION"
        )

    def speak_calendar_conversation_retry(self):
        """Ask the current Calendar clarification again after STT failure."""
        task = self.conversation_session.get_conversation_task() if self.conversation_session is not None else None

        if task is None:
            return

        field = getattr(task, "pending_clarification", "")
        reply = "다시 한 번 말씀해 주세요."

        if field:
            reply = f"다시 한 번 말씀해 주세요. {question_for_field(field)}"
        elif getattr(task, "state", "") == "WAIT_CONFIRMATION":
            reply = "다시 한 번 말씀해 주세요. 등록할까요?"

        trace_event(
            "conversation.retry",
            task_id=getattr(task, "id", ""),
            state=getattr(task, "state", ""),
            pending_clarification=field,
            reason="stt_failed",
        )
        self.speak_reply(reply)

    def advance_pending_action_turn(self):
        """Age the pending confirmation action."""
        if self.conversation_session is None:
            return

        self.conversation_session.advance_pending_action_turn()

    def speak_pending_action_retry(self):
        """Ask for confirmation again after STT failure."""
        pending_action = self.conversation_session.get_pending_action() if self.conversation_session is not None else None
        reply = f"다시 한 번 말씀해 주세요. {pending_action_confirmation_question(pending_action)}"
        trace_event("voice.pending_action.retry", reason="stt_failed")
        self.speak_reply(reply)

    def try_pending_action_confirmation_reply(self, user_message):
        """Execute or cancel a pending action from short confirmation text."""
        if self.conversation_session is None:
            return None

        pending_action = self.conversation_session.get_pending_action()

        if pending_action is None:
            return None

        action_name = format_pending_action_name(pending_action)
        decision = confirmation_decision(user_message)
        trace_event(
            "voice.confirmation.decision",
            pending_action=action_name,
            text=user_message,
            decision=decision,
        )

        if decision == "yes":
            trace_event("voice.confirmation.execute", pending_action=action_name)
            self.conversation_session.clear_pending_action()
            return self.execute_pending_action(pending_action)

        if decision == "no":
            self.conversation_session.clear_pending_action()
            return "취소했습니다."

        return pending_action_confirmation_question(pending_action)

    def execute_pending_action(self, pending_action):
        """Execute a confirmed pending action."""
        if self.intent_runtime is None:
            return "실행할 수 있는 런타임이 없습니다."

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None:
            return "실행할 수 있는 도구가 없습니다."

        started = perf_counter()
        result = dispatcher.execute(
            ToolRequest(
                tool_name=pending_action.get("ability", ""),
                input_data=dict(pending_action.get("input_data", {}), _confirmed=True),
            )
        )
        duration_ms = int((perf_counter() - started) * 1000)

        if not getattr(result, "success", False):
            return getattr(result, "error", "실행에 실패했습니다.")

        output = getattr(result, "output", None)
        self.remember_calendar_tool_output(pending_action, output)
        self.store_pending_action_task_history(dispatcher, pending_action, result, duration_ms)

        continuation_reply = self.execute_pending_plan_continuation(pending_action, result)

        if continuation_reply:
            return continuation_reply

        if hasattr(output, "to_natural_language"):
            return output.to_natural_language()

        return str(output)

    def store_pending_action_task_history(self, dispatcher, pending_action, result, duration_ms):
        """Store a lightweight RuntimeTask for confirmed one-step mutations."""
        ability = str(pending_action.get("ability", "") or "")
        action = str(pending_action.get("action", "") or "")

        if ability == "":
            return False

        status = TaskState.SUCCESS if getattr(result, "success", False) else TaskState.FAILED
        record = TaskStepRecord(
            step_index=1,
            tool_name=ability,
            action=action,
            status=status,
            attempts=1,
            duration_ms=int(duration_ms),
            error=getattr(result, "error", ""),
        )
        task = RuntimeTask(
            id="",
            goal=f"{ability}.{action}",
            status=status,
            completed_steps=(1,) if status == TaskState.SUCCESS else (),
            failed_steps=() if status == TaskState.SUCCESS else (1,),
            step_records=(record,),
            duration_ms=int(duration_ms),
        )
        history = getattr(dispatcher, "task_history", None)

        if history is not None and hasattr(history, "add"):
            history.add(task)

        if self.conversation_session is not None:
            self.conversation_session.set_last_task(task.to_dict())

        return True

    def execute_pending_plan_continuation(self, pending_action, confirmed_tool_result):
        """Resume remaining plan steps after a confirm-required step succeeds."""
        plan = pending_action.get("plan")
        step_index = int(pending_action.get("step_index", 0) or 0)

        if plan is None or step_index <= 0 or step_index >= len(getattr(plan, "steps", []) or []):
            return ""

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None:
            return ""

        context = {}
        confirmed_step = list(getattr(plan, "steps", []) or [])[step_index - 1]
        dispatcher.task_runner.update_context(context, confirmed_step, confirmed_tool_result)
        confirmed_step_result = PlanStepResult(
            step_index=confirmed_step.index,
            tool_name=confirmed_step.tool_name,
            success=getattr(confirmed_tool_result, "success", False),
            response=get_tool_result_response(confirmed_tool_result),
            tool_result=confirmed_tool_result,
            error=getattr(confirmed_tool_result, "error", ""),
        )
        plan_result = dispatcher.execute_plan(
            plan,
            confirmed=True,
            start_index=step_index,
            initial_context=context,
            pre_step_results=[confirmed_step_result],
        )
        return getattr(plan_result, "response", "")

    def remember_calendar_tool_output(self, pending_action, output):
        """Store confirmed Calendar create/list results for follow-up reminders."""
        if self.conversation_session is None:
            return False

        if str(pending_action.get("ability", "")) != "calendar":
            return False

        data = getattr(output, "data", None)
        return self.store_calendar_result(data)

    def remember_recalled_memory(self, intent_result):
        """Store the last recalled memory entry for follow-up questions."""
        entry = extract_recalled_memory_entry(intent_result)

        if entry is None or self.conversation_session is None:
            return False

        memory_date = extract_memory_date(entry)

        if memory_date == "":
            return False

        self.conversation_session.set_last_memory_result({
            "key": getattr(entry, "key", ""),
            "value": getattr(entry, "value", ""),
            "date": memory_date,
            "category": getattr(entry, "category", ""),
            "scope": getattr(entry, "scope", ""),
        })
        return True

    def try_memory_date_elapsed_reply(self, user_message):
        """Answer elapsed-date follow-ups from the last recalled memory."""
        if self.conversation_session is None:
            return None

        if not is_memory_date_elapsed_question(user_message):
            return None

        memory = self.conversation_session.get_last_memory_result() or {}
        source = "last_memory_result"

        if not is_valid_memory_date_payload(memory):
            inferred_key = infer_memory_date_elapsed_key(user_message)
            memory = self.recall_memory_date_by_key(inferred_key)
            source = "direct_key" if memory else ""

        trace_event(
            "memory.elapsed_intent",
            matched=bool(memory),
            source=source,
        )
        memory_date = str(memory.get("date", ""))

        if not is_iso_date(memory_date):
            return None

        current_date = today()
        elapsed_days = elapsed_days_since(memory_date, current_date=current_date)
        trace_event(
            "memory.date_elapsed",
            key=memory.get("key", ""),
            start_date=memory_date,
            current_date=current_date,
            elapsed_days=elapsed_days,
        )
        return f"{format_korean_date(current_date)} 기준 {elapsed_days}일 지났습니다."

    def remember_calendar_result(self, intent_result):
        """Store the last listed calendar events for follow-up questions."""
        calendar_result = extract_calendar_result(intent_result)

        if calendar_result is None:
            return False

        return self.store_calendar_result(calendar_result)

    def remember_reminder_result(self, intent_result):
        """Store the last Reminder result for relative follow-ups."""
        if self.conversation_session is None:
            return False

        reminder = extract_reminder_result(intent_result)

        if reminder is None:
            return False

        self.conversation_session.set_last_reminder(reminder)
        return True

    def remember_runtime_task(self, intent_result):
        """Store the last RuntimeTask summary for relative task references."""
        if self.conversation_session is None:
            return False

        task = getattr(intent_result, "task", None)

        if task is None:
            return False

        if hasattr(task, "to_dict"):
            self.conversation_session.set_last_task(task.to_dict())
        else:
            self.conversation_session.set_last_task({"id": getattr(task, "id", ""), "status": str(getattr(task, "status", ""))})

        return True

    def store_calendar_result(self, calendar_result):
        """Store CalendarResult events for follow-up questions."""
        if calendar_result is None:
            return False

        events = [
            {
                "id": getattr(event, "id", ""),
                "title": getattr(event, "title", ""),
                "date": getattr(event, "date", ""),
                "time": getattr(event, "time", ""),
                "location": getattr(event, "location", ""),
                "participants": list(getattr(event, "participants", []) or []),
            }
            for event in getattr(calendar_result, "events", [])
        ]

        if len(events) == 0:
            return False

        self.runtime_last_calendar_result = {"events": events}
        self.runtime_last_calendar_event = events[0]

        if self.conversation_session is not None:
            self.conversation_session.set_last_calendar_result(self.runtime_last_calendar_result)
            self.conversation_session.set_last_calendar_event(self.runtime_last_calendar_event)

        return True

    def try_calendar_reminder_follow_up_reply(self, user_message):
        """Create a reminder for the last calendar event from a short follow-up."""
        if self.conversation_session is None or self.intent_runtime is None:
            return None

        remind_before = parse_reminder_before_follow_up(user_message)

        if remind_before is None:
            return None

        calendar = self.conversation_session.get_last_calendar_result() or {}
        events = calendar.get("events", [])

        if len(events) == 0:
            return None

        event = events[0]
        event_date = event.get("date", "")
        event_time = event.get("time", "") or "00:00"

        if event_date == "":
            return None

        if len(event_time.split(":")) == 2:
            event_time = f"{event_time}:00"

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None:
            return None

        trace_event(
            "reminder.follow_up",
            source="last_calendar_result",
            title=event.get("title", ""),
            remind_before=remind_before,
        )
        result = dispatcher.execute(
            ToolRequest(
                tool_name="reminder",
                input_data={
                    "action": "create",
                    "title": event.get("title", ""),
                    "datetime": f"{event_date}T{event_time}",
                    "remind_before": remind_before,
                    "raw_text": user_message,
                },
            )
        )

        if not getattr(result, "success", False):
            return getattr(result, "error", "알림 등록에 실패했습니다.")

        output = getattr(result, "output", None)

        if hasattr(output, "to_natural_language"):
            return output.to_natural_language()

        return "알림을 등록했습니다."

    def try_calendar_follow_up_reply(self, user_message):
        """Answer follow-up questions about the last calendar result."""
        if self.conversation_session is None:
            return None

        index = parse_calendar_follow_up_index(user_message)

        if index < 0:
            return None

        calendar = self.conversation_session.get_last_calendar_result() or {}
        events = calendar.get("events", [])

        if index >= len(events):
            return "해당 순서의 일정은 없습니다."

        event = events[index]
        time_text = event.get("time", "")
        title = event.get("title", "")

        if time_text:
            return f"{index + 1}번째 일정은 {time_text} {title}입니다."

        return f"{index + 1}번째 일정은 {title}입니다."

    def try_calendar_update_reply(self, user_message):
        """Patch or delete the last referenced Calendar event."""
        if self.conversation_session is None or self.intent_runtime is None:
            return None

        calendar_event = self.get_last_calendar_event_context()
        update_input = build_calendar_update_input(user_message, calendar_event)

        if update_input is None:
            return None

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None:
            return None

        trace_event(
            "conversation.update",
            source="last_calendar_event",
            action=update_input.get("action", ""),
            event_id=update_input.get("event_id", ""),
            patch={key: value for key, value in update_input.items() if key not in ["action", "event_id", "raw_text"]},
        )
        result = dispatcher.execute(ToolRequest(tool_name="calendar", input_data=update_input))

        if not getattr(result, "success", False):
            return getattr(result, "error", "일정 수정에 실패했습니다.")

        output = getattr(result, "output", None)
        metadata = getattr(output, "metadata", {}) or {}

        if metadata.get("permission") == "confirm_required":
            self.conversation_session.set_pending_action(
                {
                    "ability": "calendar",
                    "action": update_input.get("action", ""),
                    "input_data": update_input,
                }
            )
            data = getattr(output, "data", None)
            return data.to_natural_language() if hasattr(data, "to_natural_language") else "확인이 필요합니다."

        data = getattr(output, "data", None)
        self.store_calendar_result(data)

        if hasattr(data, "to_natural_language"):
            return data.to_natural_language()

        return str(data or "")

    def get_last_calendar_event_context(self):
        """Return the most recent Calendar event from session or runtime memory."""
        if self.conversation_session is not None:
            calendar_event = self.conversation_session.get_last_calendar_event() or {}

            if calendar_event:
                return calendar_event

        return self.runtime_last_calendar_event or {}

    def recall_memory_date_by_key(self, key):
        """Recall one date memory by inferred key through the Memory Ability path."""
        if key == "" or self.intent_runtime is None:
            return {}

        dispatcher = getattr(self.intent_runtime, "tool_dispatcher", None)

        if dispatcher is None:
            return {}

        result = dispatcher.execute(
            ToolRequest(
                tool_name="memory",
                input_data={
                    "action": "recall",
                    "key": key,
                    "scope": "long_term",
                },
            )
        )

        if not getattr(result, "success", False):
            return {}

        output = getattr(result, "output", None)
        data = getattr(output, "data", None)
        entry = getattr(data, "entry", None)

        if not getattr(data, "found", False) or entry is None:
            return {}

        memory_date = extract_memory_date(entry)

        if memory_date == "":
            return {}

        return {
            "key": getattr(entry, "key", ""),
            "value": getattr(entry, "value", ""),
            "date": memory_date,
            "category": getattr(entry, "category", ""),
            "scope": getattr(entry, "scope", ""),
        }

    def advance_last_memory_result_turn(self):
        """Age session-scoped memory context after a follow-up turn."""
        if self.conversation_session is None:
            return

        self.conversation_session.advance_memory_result_turn()

    def publish_conversation_event(self, event_type):
        """Publish conversation lifecycle events."""
        if self.diagnostics_collector is None:
            return

        if not hasattr(self.diagnostics_collector, "publish"):
            return

        self.diagnostics_collector.publish(
            event_type,
            {
                "conversation": self.conversation_session.to_dict()
                if self.conversation_session is not None
                else None,
            },
        )

    def get_fallback_name(self):
        """Return a readable fallback provider name."""
        provider_name = self.get_provider_name()

        if provider_name == "mock":
            return "mock_llm"

        if provider_name.endswith("_llm"):
            return provider_name

        return f"{provider_name}_llm"

    def get_provider_name(self):
        """Return a readable active chat provider name."""
        provider = getattr(self.chat_service, "provider", None)
        metadata = getattr(provider, "last_metadata", None)
        provider_name = getattr(metadata, "provider_name", "")

        if provider_name == "":
            provider_name = getattr(provider, "provider_name", "")

        if provider_name == "":
            provider_name = provider.__class__.__name__ if provider is not None else "llm"

        return provider_name

    def get_session_id(self):
        """Return the current voice session ID when available."""
        if self.voice_session is None:
            return ""

        return getattr(self.voice_session, "session_id", "")

    def log_event(self, message):
        """Publish a diagnostics event when diagnostics is available."""
        if self.diagnostics_collector is None:
            return

        self.diagnostics_collector.log_event(message)


def choose_status(new_status, current_status):
    """Return the new status when provided, otherwise keep the current status."""
    if new_status is None:
        return current_status

    return new_status


def should_skip_voice_message(message):
    """Return whether STT output should stop before LLM or TTS."""
    text = str(message).strip()

    if text == "":
        return True

    lowered = text.lower()
    skipped_prefixes = [
        "speech recognition failed:",
        "microphone input failed:",
        "speechrecognition package is not installed.",
        "openai stt provider is not implemented yet.",
    ]

    return any(lowered.startswith(prefix) for prefix in skipped_prefixes)


def contains_any(text, tokens):
    """Return whether any token is present in text."""
    return any(token in str(text or "") for token in tokens)


def build_calendar_update_input(message, calendar_event):
    """Return Calendar update/delete input for relative event references."""
    if not calendar_event:
        return None

    text = str(message or "").strip()

    if text == "":
        return None

    event_id = str(calendar_event.get("id", "") or "").strip()

    if event_id == "" and str(calendar_event.get("title", "") or "").strip() == "":
        return None

    if is_calendar_delete_update_text(text):
        return {
            "action": "delete",
            "event_id": event_id,
            "title": "" if event_id else calendar_event.get("title", ""),
            "raw_text": text,
        }

    if not is_calendar_patch_update_text(text):
        return None

    patch = extract_calendar_update_patch(text, calendar_event)

    if len(patch) == 0:
        return None

    patch.update(
        {
            "action": "update",
            "event_id": event_id,
            "raw_text": text,
        }
    )

    if event_id == "":
        patch["title"] = patch.get("title") or calendar_event.get("title", "")

    return patch


def is_calendar_delete_update_text(text):
    """Return whether text asks to delete the referenced calendar event."""
    return contains_any(text, ["삭제", "지워", "취소"]) and contains_any(
        text,
        ["그거", "그 일정", "그 약속", "방금", "일정", "약속"],
    )


def is_calendar_patch_update_text(text):
    """Return whether text asks to patch a referenced calendar event."""
    return contains_any(text, ["바꿔", "변경", "수정", "말고", "아니고", "추가", "빼", "제외"])


def extract_calendar_update_patch(text, calendar_event):
    """Extract a partial Calendar patch from a short correction utterance."""
    patch = {}
    fields = extract_calendar_fields(text)
    date_value = parse_calendar_update_date(text) or fields.get(FIELD_DATE, "")
    time_value = parse_calendar_update_time(text) or fields.get(FIELD_TIME, "")
    location = parse_calendar_update_location(text)
    participants = parse_calendar_update_participants(text, calendar_event)

    if date_value:
        patch[FIELD_DATE] = date_value
    if time_value:
        patch[FIELD_TIME] = time_value
    if location:
        patch[FIELD_LOCATION] = location
    if participants:
        patch[FIELD_PARTICIPANTS] = participants

    title = parse_calendar_update_title(text, patch)

    if title:
        patch[FIELD_TITLE] = title

    return patch


def parse_calendar_update_date(text):
    """Parse compact Korean date corrections."""
    current = date.today()

    if "모레" in text:
        return (current + timedelta(days=2)).isoformat()
    if "내일" in text:
        return (current + timedelta(days=1)).isoformat()
    if "오늘" in text:
        return current.isoformat()

    month_day = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)

    if month_day:
        return date(current.year, int(month_day.group(1)), int(month_day.group(2))).isoformat()

    day_only = re.search(r"(\d{1,2})\s*일", text)

    if not day_only:
        return ""

    day = int(day_only.group(1))
    month = current.month
    year = current.year

    if day < current.day:
        month += 1

        if month > 12:
            month = 1
            year += 1

    return date(year, month, day).isoformat()


def parse_calendar_update_time(text):
    """Parse compact Korean time corrections."""
    match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?", text)

    if not match:
        return ""

    period = match.group(1) or ""
    hour = int(match.group(2))
    minute = int(match.group(3) or 0)

    if period == "오후" and hour < 12:
        hour += 12
    elif period == "오전" and hour == 12:
        hour = 0
    elif period == "" and 1 <= hour <= 6:
        hour += 12

    return f"{hour:02d}:{minute:02d}"


def parse_calendar_update_location(text):
    """Parse location patch text."""
    normalized_text = str(text or "").replace("설립", "서울역")
    explicit = re.search(r"(?:장소는|장소|위치는|위치|에서)\s*([가-힣A-Za-z0-9 ]+)", normalized_text)

    if explicit:
        return clean_calendar_update_fragment(explicit.group(1))

    directional = re.search(r"([가-힣A-Za-z0-9 ]+?)(?:으로|로)\s*(?:바꿔|변경|수정)", normalized_text)

    if not directional:
        return ""

    candidate = clean_calendar_update_fragment(directional.group(1))

    if any(token in candidate for token in ["역", "몰", "공단", "센터", "병원", "카페", "회사", "집"]):
        return candidate

    return ""


def parse_calendar_update_participants(text, calendar_event):
    """Parse participant additions/removals while preserving existing participants."""
    is_add = "추가" in text
    is_remove = contains_any(text, ["빼", "빼줘", "빼 줘", "제외", "제외해"])

    if not is_add and not is_remove:
        return []

    known_people = ["아야", "유이", "유리"]
    current = list(calendar_event.get("participants", []) or [])

    if is_remove:
        return [person for person in current if person not in text]

    for person in known_people:
        if person in text and person not in current:
            current.append(person)

    return current


def parse_calendar_update_title(text, patch):
    """Parse title patch when the update is not clearly date/time/location/participants."""
    if any(field in patch for field in [FIELD_DATE, FIELD_TIME, FIELD_LOCATION, FIELD_PARTICIPANTS]):
        return ""

    cleaned = re.split(r"(?:아니고|말고)", text)[-1]
    cleaned = clean_calendar_update_fragment(cleaned)

    if cleaned in ["", "그거", "그 일정", "그 약속", "일정", "약속"]:
        return ""

    return cleaned


def clean_calendar_update_fragment(text):
    """Remove update command suffixes from a patch fragment."""
    cleaned = str(text or "")

    for token in [
        "그거",
        "그 일정",
        "그 약속",
        "방금 만든 거",
        "방금",
        "으로",
        "로",
        "바꿔줘",
        "바꿔 줘",
        "바꿔",
        "변경해줘",
        "변경해 줘",
        "변경",
        "수정해줘",
        "수정해 줘",
        "수정",
        "추가해줘",
        "추가해 줘",
        "추가",
        "해줘",
        "해 줘",
    ]:
        cleaned = cleaned.replace(token, " ")

    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .,?!")


def is_successful_calendar_create(data):
    """Return whether CalendarResult represents a successful create."""
    return (
        getattr(data, "action", "") == "create"
        and bool(getattr(data, "success", False))
        and len(getattr(data, "events", []) or []) > 0
    )


def extract_recalled_memory_entry(intent_result):
    """Return a recalled MemoryEntry from a runtime result when present."""
    output = getattr(intent_result, "tool_output", None)
    data = getattr(output, "data", None)

    if getattr(data, "action", "") != "recall":
        return None

    if not getattr(data, "found", False):
        return None

    return getattr(data, "entry", None)


def runtime_result_from_plan_result(plan_result, plan):
    """Adapt Runtime Dispatcher PlanResult to the legacy Voice RuntimeResult shape."""
    step_results = list(getattr(plan_result, "step_results", []) or [])
    first_step = step_results[0] if step_results else None
    first_tool_result = getattr(first_step, "tool_result", None) if first_step is not None else None
    tool_name = getattr(first_step, "tool_name", "") if first_step is not None else ""
    tool_output = unwrap_tool_output(first_tool_result)

    return RuntimeResult(
        handled=True,
        tool=tool_name,
        tool_name=tool_name,
        response=getattr(plan_result, "response", ""),
        plan=plan,
        success=bool(getattr(plan_result, "success", False)),
        error=getattr(plan_result, "error", ""),
        fallback_used=False,
        tool_output=tool_output,
        task=getattr(plan_result, "task", None),
    )


def unwrap_tool_output(tool_result):
    """Return the AbilityResult stored inside a ToolResult when present."""
    if tool_result is None:
        return None

    output = getattr(tool_result, "output", None)

    if output is not None:
        return output

    return tool_result


def extract_calendar_result(intent_result):
    """Return CalendarResult from a handled runtime result when present."""
    if getattr(intent_result, "tool", "") != "calendar" and getattr(intent_result, "tool_name", "") != "calendar":
        return None

    output = getattr(intent_result, "tool_output", None)
    data = getattr(output, "data", None)

    if getattr(data, "action", "") not in ["list", "create"]:
        return None

    if len(getattr(data, "events", [])) == 0:
        return None

    return data


def extract_reminder_result(intent_result):
    """Return the last ReminderEntry from a handled runtime result when present."""
    if getattr(intent_result, "tool", "") != "reminder" and getattr(intent_result, "tool_name", "") != "reminder":
        return None

    output = getattr(intent_result, "tool_output", None)
    data = getattr(output, "data", None)
    reminders = list(getattr(data, "reminders", []) or [])

    if len(reminders) == 0:
        return None

    reminder = reminders[0]

    if hasattr(reminder, "to_dict"):
        return reminder.to_dict()

    return {
        "id": getattr(reminder, "id", ""),
        "title": getattr(reminder, "title", ""),
        "datetime": getattr(reminder, "datetime", ""),
        "trigger_time": getattr(reminder, "trigger_time", ""),
        "status": getattr(reminder, "status", ""),
    }


def extract_pending_action(intent_result):
    """Return pending action data from a confirm-required AbilityResult."""
    output = getattr(intent_result, "tool_output", None)
    metadata = getattr(output, "metadata", {}) or {}

    if metadata.get("permission") != "confirm_required":
        return None

    query = metadata.get("query")
    action = getattr(query, "action", "")
    ability = metadata.get("ability_id", getattr(intent_result, "tool", ""))

    if ability == "":
        ability = getattr(intent_result, "tool_name", "")

    pending_action = {
        "ability": ability,
        "action": action,
        "input_data": query_to_input_data(query),
    }

    plan = getattr(intent_result, "plan", None)

    if plan is not None:
        pending_action["plan"] = plan
        step_index = pending_step_index(plan, ability)
        pending_action["step_index"] = step_index

        if should_suppress_pending_calendar_auto_reminder(plan, step_index, ability):
            pending_action["input_data"]["_suppress_auto_reminder"] = True

    return pending_action


def pending_step_index(plan, ability):
    """Return the one-based step index that is waiting for confirmation."""
    for step in getattr(plan, "steps", []) or []:
        step_tool = getattr(step, "tool_name", getattr(step, "tool", ""))

        if step_tool == ability:
            try:
                return int(getattr(step, "index", 0))
            except (TypeError, ValueError):
                return 0

    return 0


def should_suppress_pending_calendar_auto_reminder(plan, step_index, ability):
    """Return whether a pending Calendar action has an explicit Reminder continuation."""
    if ability != "calendar" or step_index <= 0:
        return False

    for step in getattr(plan, "steps", []) or []:
        if getattr(step, "tool_name", getattr(step, "tool", "")) != "reminder":
            continue

        if step_index in tuple(getattr(step, "depends_on", ()) or ()):
            return True

    return False


def get_tool_result_response(tool_result):
    """Return a stable response string for a ToolResult."""
    output = getattr(tool_result, "output", None)

    if hasattr(output, "to_natural_language"):
        return output.to_natural_language()

    if output is not None:
        return str(output)

    return getattr(tool_result, "error", "")


def query_to_input_data(query):
    """Serialize a confirmable query to Tool input."""
    if hasattr(query, "workflow_key"):
        return integration_query_to_input_data(query)

    if hasattr(query, "due_at") and hasattr(query, "date_scope"):
        return todo_query_to_input_data(query)

    if hasattr(query, "display_name") and hasattr(query, "attribute"):
        return contact_query_to_input_data(query)

    return calendar_query_to_input_data(query)


def integration_query_to_input_data(query):
    """Serialize an IntegrationQuery-like object to Tool input."""
    return {
        "workflow_key": getattr(query, "workflow_key", ""),
        "action": getattr(query, "action", ""),
        "payload": dict(getattr(query, "payload", {}) or {}),
        "raw_text": getattr(query, "raw_text", ""),
        "conversation_id": getattr(query, "conversation_id", ""),
        "session_id": getattr(query, "session_id", ""),
        "workflow_id": getattr(query, "workflow_id", ""),
        "idempotency_key": getattr(query, "idempotency_key", ""),
        "max_retry": getattr(query, "max_retry", 0),
        "retry_delay_seconds": getattr(query, "retry_delay_seconds", 0.0),
        "metadata": dict(getattr(query, "metadata", {}) or {}),
    }


def extract_pending_clarification(intent_result, user_message):
    """Return clarification state to keep for the next user turn."""
    plan = getattr(intent_result, "plan", None)

    if plan is None:
        return None

    if not getattr(plan, "requires_clarification", False):
        return None

    question = str(getattr(plan, "clarification_question", "") or getattr(intent_result, "response", "") or "")
    raw_text = str(user_message or "")

    if not is_reminder_time_clarification(question, raw_text):
        return None

    title = extract_pending_reminder_title(raw_text)

    return {
        "kind": "reminder_time",
        "title": title,
        "raw_text": raw_text,
        "question": question,
    }


def is_reminder_time_clarification(question, raw_text):
    """Return whether the clarification asks for a missing reminder delay."""
    text = f"{question} {raw_text}"
    reminder_tokens = ["\uc54c\ub824", "\uc54c\ub9bc", "\uc54c\ub78c", "\ucc59\uaca8", "\ub9ac\ub9c8\uc778\ub354"]
    time_question_tokens = ["\uba87 \ubd84", "\uba87\ubd84", "\uc5b8\uc81c", "\uc774\ub530\uac00", "\uc870\uae08"]
    return any(token in text for token in reminder_tokens) and any(token in text for token in time_question_tokens)


def extract_pending_reminder_title(raw_text):
    """Extract a reminder title from the original ambiguous request."""
    text = str(raw_text or "").strip()

    if "\ubb3c" in text and ("\ub9c8\uc2dc" in text or "\uba39" in text):
        return "\ubb3c \ub9c8\uc2dc\uae30"

    cleaned = text

    for token in [
        "\uc870\uae08",
        "\uc774\ub530\uac00",
        "\uc774\ub530",
        "\uc7a0\uc2dc \ud6c4",
        "\ub098\uc911\uc5d0",
        "\uc54c\ub824\uc918",
        "\uc54c\ub824 \uc918",
        "\ucc59\uaca8\uc918",
        "\ucc59\uaca8 \uc918",
        "\ud574\uc918",
        "\ud574 \uc918",
        "\ub9d0\ud574\uc918",
        "\ub9d0\ud574 \uc918",
    ]:
        cleaned = cleaned.replace(token, " ")

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!")
    cleaned = re.sub(r"\s*(\ub77c\uace0|\ud558\ub77c\uace0)$", "", cleaned).strip()
    return cleaned or "\uc54c\ub9bc"


def parse_relative_minutes(text):
    """Parse a minute delay from a follow-up answer."""
    match = re.search(r"(\d+)\s*\ubd84", str(text or ""))

    if not match:
        return None

    try:
        minutes = int(match.group(1))
    except ValueError:
        return None

    if minutes <= 0:
        return None

    return minutes


def is_alarm_like_request(message):
    """Return whether failed routing should stay away from LLM fake success."""
    text = str(message or "").strip()

    if text == "":
        return False

    alarm_tokens = ["알람", "알림", "리마인더"]
    reminder_action_tokens = ["등록", "설정", "예약", "알려줘", "알려 줘"]
    time_tokens = ["분 뒤", "분 후", "시간 뒤", "시간 후", "분 전", "시간 전", "내일", "오늘", "오후", "오전"]

    if any(token in text for token in alarm_tokens):
        return True

    if any(token in text for token in reminder_action_tokens) and any(token in text for token in time_tokens):
        return True

    return False


def is_todo_like_failed_request(message):
    """Return whether failed routing should stay away from LLM fake success for Todo-like text."""
    text = str(message or "").strip()

    if text == "":
        return False

    todo_objects = [
        "\uc6b0\uc720",
        "\uc57d",
        "\uc7a5\ubcf4\uae30",
        "\uc0ac\uae30",
        "\ud560 \uc77c",
        "\ud560\uc77c",
        "\ud22c\ub450",
    ]
    todo_actions = [
        "\ucd94\uac00",
        "\ucd95\ud558",
        "\ub4f1\ub85d",
        "\ub123\uc5b4",
        "\uc0ad\uc81c",
        "\uc9c0\uc6cc",
        "\uc644\ub8cc",
    ]

    return any(token in text for token in todo_objects) and any(token in text for token in todo_actions)


def parse_reminder_before_follow_up(message):
    """Return remind-before minutes from a Calendar follow-up request."""
    text = str(message or "").strip()

    if text == "":
        return None

    if "알려" not in text and "알림" not in text and "알람" not in text and "리마인더" not in text:
        return None

    hour_match = re.search(r"(\d+)\s*시간\s*전", text)

    if hour_match:
        return int(hour_match.group(1)) * 60

    minute_match = re.search(r"(\d+)\s*분\s*전", text)

    if minute_match:
        return int(minute_match.group(1))

    return None


def calendar_query_to_input_data(query):
    """Serialize a CalendarQuery-like object to Tool input."""
    return {
        "action": getattr(query, "action", ""),
        "date": getattr(query, "date", ""),
        "time": getattr(query, "time", ""),
        "title": getattr(query, "title", ""),
        "description": getattr(query, "description", ""),
        "location": getattr(query, "location", ""),
        "participants": list(getattr(query, "participants", [])),
        "raw_text": getattr(query, "raw_text", ""),
        "event_id": getattr(query, "event_id", ""),
    }


def contact_query_to_input_data(query):
    """Serialize a ContactQuery-like object to Tool input."""
    return {
        "action": getattr(query, "action", ""),
        "contact_id": getattr(query, "contact_id", ""),
        "display_name": getattr(query, "display_name", ""),
        "aliases": list(getattr(query, "aliases", [])),
        "email": getattr(query, "email", ""),
        "phone": getattr(query, "phone", ""),
        "birthday": getattr(query, "birthday", ""),
        "attribute": getattr(query, "attribute", "contact"),
        "source": getattr(query, "source", "user"),
        "raw_text": getattr(query, "raw_text", ""),
    }


def todo_query_to_input_data(query):
    """Serialize a TodoQuery-like object to Tool input."""
    return {
        "action": getattr(query, "action", ""),
        "todo_id": getattr(query, "todo_id", ""),
        "title": getattr(query, "title", ""),
        "due_at": getattr(query, "due_at", ""),
        "priority": getattr(query, "priority", "normal"),
        "status": getattr(query, "status", ""),
        "date_scope": getattr(query, "date_scope", ""),
        "raw_text": getattr(query, "raw_text", ""),
    }


def is_confirmation_yes(message):
    """Return whether the text confirms a pending action."""
    text = normalize_confirmation_text(message)
    return text in ["응", "어", "그래", "좋아", "등록해", "해줘", "맞아", "예", "네"]


def is_confirmation_no(message):
    """Return whether the text rejects a pending action."""
    text = normalize_confirmation_text(message)
    return text in ["아니", "취소", "하지마", "안돼", "안 돼"]


def normalize_confirmation_text(message):
    """Normalize short confirmation text."""
    return str(message or "").strip().lower().strip(".?! ")


def format_pending_action_name(pending_action):
    """Return a readable pending action name for trace logs."""
    ability = str(pending_action.get("ability", "")).strip()
    action = str(pending_action.get("action", "")).strip()

    if ability and action:
        return f"{ability}.{action}"

    return ability or action or "unknown"


def pending_action_confirmation_question(pending_action):
    """Return a short Korean confirmation question for a pending action."""
    action = ""

    if pending_action is not None:
        action = str(pending_action.get("action", "") or "").strip()

    if action == "update":
        return "수정할까요?"

    if action == "delete":
        return "삭제할까요?"

    if action == "create":
        return "등록할까요?"

    return "진행할까요?"


def confirmation_decision(message):
    """Return yes, no, or unknown for a pending confirmation reply."""
    text = normalize_confirmation_text(message)

    if text == "":
        return "unknown"

    if confirmation_text_matches(text, confirmation_no_aliases()):
        return "no"

    if confirmation_text_matches(text, confirmation_yes_aliases()):
        return "yes"

    return "unknown"


def is_confirmation_yes(message):
    """Return whether the text confirms a pending action."""
    return confirmation_decision(message) == "yes"


def is_confirmation_no(message):
    """Return whether the text rejects a pending action."""
    return confirmation_decision(message) == "no"


def confirmation_text_matches(text, aliases):
    """Return whether normalized confirmation text contains an alias."""
    compact_text = text.replace(" ", "")

    for alias in aliases:
        normalized_alias = normalize_confirmation_text(alias)
        compact_alias = normalized_alias.replace(" ", "")

        if text == normalized_alias or compact_text == compact_alias:
            return True

        if len(compact_alias) <= 1:
            continue

        if normalized_alias and normalized_alias in text:
            return True

        if compact_alias and compact_alias in compact_text:
            return True

    return False


def confirmation_yes_aliases():
    """Return affirmative confirmation aliases."""
    return [
        "\uc751",
        "\uc6c5",
        "\uc74c",
        "\uc5b4",
        "\uc5c9",
        "\uc751\uc751",
        "\ub124",
        "\ub125",
        "\ub135",
        "\uc608",
        "\uc608\uc2a4",
        "\uc88b\uc544",
        "\uadf8\ub798",
        "\uadf8\ub7fc",
        "\ub9de\uc544",
        "\ud574",
        "\ud574\uc918",
        "\ub4f1\ub85d\ud574",
        "\ub4f1\ub85d\ud574 \uc918",
        "\uc751 \ub4f1\ub85d\ud574",
        "\uc751 \ub4f1\ub85d\ud574 \uc918",
        "\uc0ad\uc81c\ud574",
        "\uc0ad\uc81c\ud574 \uc918",
        "\uc751 \uc0ad\uc81c\ud574",
        "\uc751 \uc0ad\uc81c\ud574 \uc918",
        "\uc218\uc815\ud574",
        "\uc218\uc815\ud574 \uc918",
        "\uc751 \uc218\uc815\ud574",
        "\uc751 \uc218\uc815\ud574 \uc918",
        "\uc9c4\ud589\ud574",
        "\ud655\uc778",
        "\uc2b9\uc778",
        "gronn",
        "gron",
        "grown",
        "green",
        "\u55ef",
        "\u55ef\u55ef",
    ]


def confirmation_no_aliases():
    """Return negative confirmation aliases."""
    return [
        "\uc544\ub2c8",
        "\uc544\ub2c8\uc57c",
        "\ucde8\uc18c",
        "\ud558\uc9c0\ub9c8",
        "\uc548 \ud574",
        "\ub410\uc5b4",
        "\ubcf4\ub958",
    ]


def normalize_confirmation_text(message):
    """Normalize short confirmation text."""
    text = " ".join(str(message or "").strip().lower().strip(".?! ").split())
    return strip_latin_diacritics(text)


def strip_latin_diacritics(text):
    """Remove Latin diacritics from short STT confirmation artifacts."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return unicodedata.normalize("NFC", stripped)


def parse_calendar_follow_up_index(message):
    """Return zero-based event index from Korean follow-up text."""
    text = str(message or "").strip()

    if text == "":
        return -1

    if any(token in text for token in ["첫 번째", "첫번째", "1번째", "1번"]):
        return 0

    if any(token in text for token in ["두 번째", "두번째", "2번째", "2번", "다음"]):
        return 1

    return -1


def is_calendar_query_command_text(message):
    """Return whether a follow-up should be treated as a fresh calendar query."""
    text = str(message or "").strip()

    if text == "":
        return False

    if "\ub2e4\uc74c \uc8fc" in text or "\ub2e4\uc74c\uc8fc" in text:
        return "\uc77c\uc815" in text

    next_schedule_tokens = [
        "\ub2e4\uc74c \uc77c\uc815",
        "\ub2e4\uc74c\uc77c\uc815",
        "\ub2e4\uc74c \uc77c\uc815\uc744",
        "\ub2e4\uc74c \uc77c\uc815\uc740",
    ]
    command_tokens = [
        "\uc54c\ub824",
        "\ubcf4\uc5ec",
        "\uc870\ud68c",
        "\ucc3e\uc544",
        "\uac80\uc0c9",
        "\ubb50",
        "\uc788",
    ]

    return any(token in text for token in next_schedule_tokens) and any(
        token in text for token in command_tokens
    )


def is_todo_ordinal_or_mutation_text(message):
    """Return whether an ordinal/mutation follow-up should route to Todo instead of Calendar."""
    text = str(message or "").strip()

    if text == "":
        return False

    todo_subject_tokens = [
        "\ud560 \uc77c",
        "\ud560\uc77c",
        "\ud22c\ub450",
        "\uc7a5\ubcf4\uae30",
        "\uc6b0\uc720",
    ]
    todo_action_tokens = [
        "\uc644\ub8cc",
        "\ub05d\ub0c8",
        "\ub05d\ub0ac",
        "\ucc98\ub9ac",
        "\uc0ad\uc81c",
        "\uc9c0\uc6cc",
        "\ucde8\uc18c",
        "\ubcf5\uc6d0",
    ]

    if any(token in text for token in todo_action_tokens):
        return True

    return any(token in text for token in todo_subject_tokens) and parse_calendar_follow_up_index(text) >= 0


def extract_memory_date(entry):
    """Return the best date value from a memory entry."""
    event = getattr(entry, "event", {}) or {}
    event_date = str(event.get("date", ""))

    if is_iso_date(event_date):
        return event_date

    value = str(getattr(entry, "value", ""))

    if is_iso_date(value):
        return value

    return ""


def is_memory_date_elapsed_question(message):
    """Return whether a follow-up asks elapsed days from a recalled date."""
    text = str(message or "").strip()

    if text == "":
        return False

    return contains_elapsed_phrase(text) or infer_memory_date_elapsed_key(text) != ""


def is_valid_memory_date_payload(memory):
    """Return whether a memory payload contains a usable date."""
    if not isinstance(memory, dict):
        return False

    return is_iso_date(str(memory.get("date", "")))


def infer_memory_date_elapsed_key(message):
    """Infer a memory date key from direct elapsed-date questions."""
    text = str(message or "").strip()

    if text == "":
        return ""

    if contains_person_alias(text, ["아야", "아야랑", "아야와"]) and contains_event_phrase(text) and contains_elapsed_phrase(text):
        return "relationship.aya.first_meeting_date"

    return ""


def contains_person_alias(text, aliases):
    """Return whether text mentions a known person alias."""
    return any(alias in text for alias in aliases)


def contains_event_phrase(text):
    """Return whether text mentions an event relation."""
    return any(
        phrase in text
        for phrase in [
            "만난 뒤",
            "만난 후",
            "만난 지",
            "만난",
            "지난 지",
        ]
    )


def contains_elapsed_phrase(text):
    """Return whether text asks about elapsed time."""
    return any(
        phrase in text
        for phrase in [
            "며칠이나 됐어",
            "며칠 됐어",
            "며칠",
            "몇 일",
            "얼마나 됐어",
            "얼마나 됐",
            "얼마나 지났",
            "지난 지",
            "지났어",
            "됐어",
            "오늘 기준",
        ]
    )


def format_reminder_offset(minutes):
    """Return a natural Korean reminder offset label."""
    minutes = int(minutes)

    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours}시간"

    return f"{minutes}분"


DEBUG_SEPARATOR = "\u2501" * 18
