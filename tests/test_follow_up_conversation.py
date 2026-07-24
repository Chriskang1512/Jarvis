import unittest
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from jarvis.abilities import AbilityRegistry
from jarvis.abilities.native.calendar import CalendarAbility, MockCalendarProvider
from jarvis.abilities.native.calendar.result import CalendarEvent, CalendarResult
from jarvis.abilities.native.mail import MailAbility
from jarvis.abilities.native.mail.result import MailMessage, MailResult
from jarvis.abilities.native.memory import InMemoryStorage, MemoryAbility
from jarvis.abilities.native.reminder import ReminderAbility
from jarvis.abilities.native.todo import TodoAbility
from jarvis.abilities.result import AbilityResult
from jarvis.brain import IntentRuntime
from jarvis.diagnostics import DiagnosticsCollector
from jarvis.diagnostics.runtime_console import RuntimeDevConsole
from jarvis.native.reminder import ReminderEngine, ReminderQueue
from jarvis.runtime.intent import IntentParseResult
from jarvis.runtime.tool_dispatcher import RuntimeToolDispatcher
from jarvis.tools import ToolDispatcher, ToolRegistry
from jarvis.voice import CONVERSATION_CLOSED, CONVERSATION_FOLLOW_UP
from jarvis.voice import create_conversation_session
from jarvis.voice.conversation import DEFAULT_LAST_MEMORY_RESULT_TURNS
from jarvis.runtime.conversation_task import confirmation_decision as calendar_confirmation_decision
from jarvis.runtime.conversation_task import (
    FIELD_TITLE,
    FIELD_TIME,
    extract_calendar_fields,
    start_calendar_conversation_task,
    should_start_calendar_conversation,
    update_calendar_conversation_task,
)
from jarvis.voice.pipeline import (
    VoicePipeline,
    build_calendar_update_input,
    confirmation_decision,
    extract_pending_action,
    is_unprompted_short_follow_up_noise,
    mail_reply_offer_decision,
    runtime_result_from_plan_result,
    should_skip_embedded_google_calendar_reminder_continuation,
)


class TestFollowUpConversationMode(unittest.TestCase):
    """Test v0.5.0 Beta.5.3 follow-up conversation mode."""

    def test_calendar_update_can_remove_named_participant(self):
        """Check relative Calendar updates can remove one participant."""
        update_input = build_calendar_update_input(
            "아야 빼줘",
            {
                "id": "mock-1",
                "title": "아야 유이 만나기",
                "participants": ["아야", "유이"],
            },
        )

        self.assertIsNotNone(update_input)
        self.assertEqual(update_input["action"], "update")
        self.assertEqual(update_input["participants"], ["유이"])

    def test_confirmation_decision_accepts_openai_short_yes_artifact(self):
        """Check OpenAI STT artifacts for '응' can confirm an action."""
        self.assertEqual(confirmation_decision("嗯"), "yes")
        self.assertEqual(calendar_confirmation_decision("嗯"), "yes")
        self.assertEqual(confirmation_decision("음?"), "yes")
        self.assertEqual(calendar_confirmation_decision("음?"), "yes")

    def test_confirmation_decision_does_not_match_short_alias_inside_words(self):
        """Check one-syllable yes aliases do not confirm unrelated words."""
        self.assertEqual(confirmation_decision("다음"), "unknown")
        self.assertEqual(calendar_confirmation_decision("다음"), "")

    def test_mail_reply_offer_treats_stt_yak_sagi_as_no_only_in_offer_context(self):
        self.assertEqual(confirmation_decision("약 사기."), "unknown")
        self.assertEqual(mail_reply_offer_decision("약 사기."), "no")

        session = create_conversation_session(follow_up_timeout=8)
        session.start()
        session.set_pending_clarification({"kind": "mail_reply_offer"})
        pipeline = VoicePipeline(
            wake_listener=None,
            stt_provider=None,
            chat_service=None,
            tts_provider=None,
            conversation_session=session,
        )

        self.assertTrue(pipeline.should_listen_for_confirmation())
        self.assertEqual(pipeline.try_pending_clarification_reply("약 사기."), "알겠습니다.")
        self.assertIsNone(session.get_pending_clarification())

    def test_unprompted_short_follow_up_noise_blocks_bare_todo_subject(self):
        """Check a bare Todo subject is ignored unless it has an action verb."""
        self.assertTrue(is_unprompted_short_follow_up_noise("\ud560 \uc77c"))
        self.assertTrue(is_unprompted_short_follow_up_noise("\ud560\uc77c"))
        self.assertFalse(is_unprompted_short_follow_up_noise("\ud560 \uc77c \uc54c\ub824\uc918"))

    def test_calendar_confirmation_noise_does_not_overwrite_title(self):
        """Check unknown short confirmation noise is not stored as a title."""
        task = start_calendar_conversation_task("내일 오후 3시에 만나기 일정 등록해")
        update_calendar_conversation_task(task, "아야")
        update_calendar_conversation_task(task, "잠실")
        original_title = task.fields[FIELD_TITLE]

        reply = update_calendar_conversation_task(task, "Ö?")

        self.assertEqual(task.fields[FIELD_TITLE], original_title)
        self.assertTrue(reply)

    def test_calendar_conversation_normalizes_aja_meeting_title(self):
        """Check Calendar-only STT cleanup maps Aja/나의 meeting artifacts to 아야."""
        task = start_calendar_conversation_task("내일 오후 3시에 나의 만나기 일정 등록해")

        self.assertEqual(task.fields[FIELD_TITLE], "아야 만나기")

    def test_calendar_conversation_extracts_spoken_korean_time(self):
        """Check spoken Korean time words are parsed during follow-up collection."""
        self.assertEqual(extract_calendar_fields("내일 오후 세시")[FIELD_TIME], "15:00")
        self.assertEqual(extract_calendar_fields("오후 세시")[FIELD_TIME], "15:00")
        self.assertEqual(extract_calendar_fields("세 시")[FIELD_TIME], "15:00")

    def test_conversation_session_creation_and_timeout(self):
        """Check ConversationSession tracks state and timeout."""
        session = create_conversation_session(follow_up_timeout=8)

        session.start()
        session.enter_follow_up()

        self.assertEqual(session.state, CONVERSATION_FOLLOW_UP)
        self.assertEqual(session.follow_up_timeout, 8.0)
        self.assertGreater(session.remaining_follow_up_seconds(), 0.0)

        session.close()

        self.assertEqual(session.state, CONVERSATION_CLOSED)

    def test_follow_up_question_does_not_require_wake_word(self):
        """Check one wake word can handle initial and follow-up turns."""
        wake_listener = CountingWakeListener()
        stt_provider = FollowUpSTTProvider(
            first="hello",
            follow_ups=["what time is it", ""],
        )
        chat_service = CapturingChatService()
        diagnostics = DiagnosticsCollector()
        pipeline = VoicePipeline(
            wake_listener=wake_listener,
            stt_provider=stt_provider,
            chat_service=chat_service,
            tts_provider=CapturingTTSProvider(),
            diagnostics_collector=diagnostics,
            follow_up_timeout=8,
        )

        reply = pipeline.run_once()

        events = [event.event_type for event in diagnostics.get_snapshot().published_events]
        self.assertEqual(reply, "reply: hello")
        self.assertEqual(wake_listener.calls, 1)
        self.assertEqual(chat_service.messages, ["hello", "what time is it"])
        self.assertEqual(pipeline.conversation_session.state, CONVERSATION_CLOSED)
        self.assertIn("conversation.started", events)
        self.assertIn("conversation.follow_up", events)
        self.assertIn("conversation.closed", events)

    def test_follow_up_timeout_closes_session(self):
        """Check empty follow-up input closes the session."""
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(first="hello", follow_ups=[""]),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(pipeline.conversation_session.state, CONVERSATION_CLOSED)

    def test_last_memory_result_is_session_scoped_and_expires_by_turns(self):
        """Check last memory context is scoped to one wake session."""
        session = create_conversation_session(follow_up_timeout=8)
        session.set_last_memory_result({"key": "relationship.aya.first_meeting_date", "date": "2026-03-26"})

        self.assertEqual(session.get_last_memory_result()["date"], "2026-03-26")
        self.assertEqual(session.last_memory_result_turns_remaining, DEFAULT_LAST_MEMORY_RESULT_TURNS)

        session.advance_memory_result_turn()
        self.assertIsNotNone(session.get_last_memory_result())
        session.advance_memory_result_turn()

        self.assertIsNone(session.get_last_memory_result())

    def test_last_memory_result_clears_on_close_and_new_session(self):
        """Check memory follow-up context does not leak across wake sessions."""
        session = create_conversation_session(follow_up_timeout=8)
        session.set_last_memory_result({"key": "relationship.aya.first_meeting_date", "date": "2026-03-26"})

        session.close()
        next_session = create_conversation_session(follow_up_timeout=8)

        self.assertIsNone(session.get_last_memory_result())
        self.assertIsNone(next_session.get_last_memory_result())

    def test_runtime_console_renders_conversation_state(self):
        """Check dev console shows conversation session state."""
        conversation = create_conversation_session(follow_up_timeout=8)
        conversation.start()
        conversation.enter_follow_up()

        output = RuntimeDevConsole().render(conversation=conversation)

        self.assertIn("Conversation", output)
        self.assertIn("Session", output)
        self.assertIn(conversation.session_id, output)
        self.assertIn("State", output)
        self.assertIn("Follow-up", output)
        self.assertIn("Remaining", output)

    def test_memory_date_elapsed_follow_up_uses_calculator_without_llm(self):
        """Check elapsed-date follow-up uses recalled memory context."""
        previous_date = os.environ.get("JARVIS_CURRENT_DATE", "")
        os.environ["JARVIS_CURRENT_DATE"] = "2026-07-09"
        storage = InMemoryStorage()
        ability = MemoryAbility(storage=storage)
        ability.execute(
            {
                "text": "아야랑 처음 만난 날은 2026년 3월 26일이야. 기억해.",
            }
        )
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(ability)
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        stt_provider = FollowUpSTTProvider(
            first="아야 처음 만난 날이 언제야",
            follow_ups=["오늘 기준으로 며칠이나 됐어?", ""],
        )
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=stt_provider,
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        try:
            pipeline.run_once()
        finally:
            if previous_date == "":
                os.environ.pop("JARVIS_CURRENT_DATE", None)
            else:
                os.environ["JARVIS_CURRENT_DATE"] = previous_date

        self.assertEqual(chat_service.messages, [])
        self.assertGreaterEqual(len(tts_provider.spoken), 2)
        self.assertIn("105일 지났습니다", tts_provider.spoken[1])

    def test_memory_date_elapsed_direct_question_infers_key_without_last_memory_result(self):
        """Check direct elapsed-date questions can infer and recall a memory key."""
        previous_date = os.environ.get("JARVIS_CURRENT_DATE", "")
        os.environ["JARVIS_CURRENT_DATE"] = "2026-07-09"
        storage = InMemoryStorage()
        ability = MemoryAbility(storage=storage)
        ability.execute(
            {
                "text": "아야랑 처음 만난 날은 2026년 3월 26일이야. 기억해.",
            }
        )
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(ability)
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="아야 만난 뒤 며칠이나 됐어",
                follow_ups=[""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        try:
            pipeline.run_once()
        finally:
            if previous_date == "":
                os.environ.pop("JARVIS_CURRENT_DATE", None)
            else:
                os.environ["JARVIS_CURRENT_DATE"] = previous_date

        self.assertEqual(chat_service.messages, [])
        self.assertGreaterEqual(len(tts_provider.spoken), 1)
        self.assertIn("2026년 7월 9일 기준 105일 지났습니다", tts_provider.spoken[0])

    def test_calendar_follow_up_first_and_next_event_use_session_result(self):
        """Check calendar list follow-ups use session-scoped CalendarResult."""
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=MockCalendarProvider()))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="오늘 일정 알려줘",
                follow_ups=["첫 번째는?", "다음 일정은?", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(chat_service.messages, [])
        self.assertIn("오늘 일정은 2건입니다", tts_provider.spoken[0])
        self.assertIn("1번째 일정은 10:00 회의입니다", tts_provider.spoken[1])
        self.assertIn("2번째 일정은 15:00 치과입니다", tts_provider.spoken[2])

    def test_mail_read_reply_offer_collects_body_then_confirms(self):
        """Check a selected mail offers reply composition before final confirmation."""
        provider = FollowUpMailProvider()
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(MailAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="최근 메일 알려줘",
                follow_ups=["첫 번째 메일 읽어줘", "응", "확인했습니다", "아니", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )
        pipeline.runtime_last_calendar_result = {
            "events": [
                {
                    "id": "old-event",
                    "title": "Old calendar event",
                    "date": "2026-07-24",
                    "time": "10:00",
                }
            ]
        }

        pipeline.run_once()

        self.assertTrue(any("테스트 본문" in text for text in tts_provider.spoken))
        self.assertFalse(any("아야," in text for text in tts_provider.spoken))
        self.assertTrue(any("답장하시겠습니까?" in text for text in tts_provider.spoken))
        self.assertIn("어떤 내용으로 답장할까요?", tts_provider.spoken)
        self.assertTrue(any("답장을 보낼까요" in text for text in tts_provider.spoken))
        self.assertIn("취소했습니다.", tts_provider.spoken)
        self.assertEqual(provider.reply_calls, 0)

    def test_bare_ordinal_read_uses_latest_mail_list_over_stale_calendar(self):
        """Check Mail becomes the ordinal focus after listing over old Calendar context."""
        provider = FollowUpMailProvider()
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(MailAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ucd5c\uadfc \uba54\uc77c \uc54c\ub824\uc918",
                follow_ups=["\uccab \ubc88\uc9f8 \uc77d\uc5b4\uc918", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry)),
            follow_up_timeout=8,
        )
        pipeline.runtime_last_calendar_result = {
            "events": [
                {
                    "id": "old-event",
                    "title": "Old calendar event",
                    "date": "2026-07-24",
                    "time": "10:00",
                }
            ]
        }

        pipeline.run_once()

        self.assertTrue(any("\ud14c\uc2a4\ud2b8 \ubcf8\ubb38" in text for text in tts_provider.spoken))
        self.assertFalse(any("Old calendar event" in text for text in tts_provider.spoken))

    def test_calendar_pending_create_survives_stt_failure_and_confirms_yes(self):
        """Check pending calendar create retries after STT failure and executes on yes."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="내일 오후 3시에 아야 유이 만나기 일정 등록해",
                follow_ups=["Speech recognition failed: unknown value", "응", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(chat_service.messages, [])
        self.assertIn("등록할까요", tts_provider.spoken[0])
        self.assertIn("다시 한 번 말씀해 주세요", tts_provider.spoken[1])
        self.assertIn("일정을 등록했습니다", tts_provider.spoken[2])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].time, "15:00")
        self.assertEqual(provider.events[0].title, "아야 유이 만나기")


    def test_pending_confirmation_voice_turn_runs_before_llm_fallback(self):
        """Check a fresh voice turn confirms pending actions before chat fallback."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        session = create_conversation_session(follow_up_timeout=8)
        session.start()
        session.set_pending_action(
            {
                "ability": "calendar",
                "action": "create",
                "input_data": {
                    "action": "create",
                    "date": "2099-07-10",
                    "time": "15:00",
                    "title": "meeting",
                    "description": "",
                    "location": "",
                    "participants": [],
                    "raw_text": "create meeting",
                },
            }
        )
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(first="\uc751 \ub4f1\ub85d\ud574", follow_ups=[]),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
            conversation_session=session,
        )

        reply = pipeline.process_voice_turn()

        self.assertEqual(chat_service.messages, [])
        self.assertIn("\uc77c\uc815\uc744 \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4", reply)
        self.assertEqual(tts_provider.spoken, [reply])
        self.assertEqual(len(provider.events), 1)
        self.assertIsNone(session.get_pending_action())

    def test_runtime_plan_calendar_confirmation_is_saved_and_confirmed(self):
        """Check planner results keep confirm metadata for the follow-up yes turn."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c 3\uc2dc\uc5d0 \uc57d\uc18d \uc7a1\uc544 \uc918",
                follow_ups=["\uc751 \ub4f1\ub85d\ud574", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(chat_service.messages, [])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, (datetime.now().date() + timedelta(days=1)).isoformat())
        self.assertEqual(provider.events[0].time, "15:00")
        self.assertEqual(provider.events[0].title, "\uc57d\uc18d")
        self.assertIsNone(pipeline.conversation_session.get_pending_action())
        self.assertTrue(any("\uc77c\uc815\uc744 \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4" in text for text in tts_provider.spoken))

    def test_runtime_plan_calendar_delete_confirmation_returns_deleted_message(self):
        """Check confirmed generic day delete says deleted instead of asking again."""
        provider = MockCalendarProvider()
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc624\ub298 \uc77c\uc815 \ubaa8\ub450 \uc0ad\uc81c",
                follow_ups=["\uc751 \uc0ad\uc81c\ud574", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(chat_service.messages, [])
        self.assertEqual(provider.events, [])
        self.assertIsNone(pipeline.conversation_session.get_pending_action())
        self.assertTrue(any("\uc77c\uc815\uc744 \uc0ad\uc81c\ud588\uc2b5\ub2c8\ub2e4" in text for text in tts_provider.spoken))

    def test_runtime_plan_confirmation_resumes_remaining_reminder_step(self):
        """Check Calendar confirmation pauses and then resumes dependent Reminder."""
        provider = MockCalendarProvider(events=[])
        engine = ReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register(ReminderAbility(engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c 3\uc2dc\uc5d0 \uc57d\uc18d \uc7a1\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824 \uc918",
                follow_ups=["\uc751 \ub4f1\ub85d\ud574", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        reminders = engine.list(state="pending")
        self.assertEqual(chat_service.messages, [])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].title, "\uc57d\uc18d")
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].title, "\uc57d\uc18d")
        self.assertEqual(reminders[0].remind_before, 30)
        self.assertIn("\u0033\u0030\ubd84 \uc804 \uc54c\ub9bc\ub3c4 \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4", tts_provider.spoken[-1])

    def test_calendar_pending_confirmation_preserves_reminder_override(self):
        """Check Google Calendar confirmation keeps planner-owned reminder minutes."""
        provider = MockCalendarProvider(events=[])
        engine = ReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register(ReminderAbility(engine=engine))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        plan = dispatcher.create_plan(
            "\ub0b4\uc77c \uc624\ud6c4 \u0032\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \uc7a1\uace0 \ud55c \uc2dc\uac04 \uc804\uc5d0 \uc54c\ub824 \uc918"
        )

        self.assertEqual(plan.steps[0].input_data["remind_before_minutes"], 60)
        plan_result = dispatcher.execute_plan(plan)
        runtime_result = runtime_result_from_plan_result(plan_result, plan)
        pending_action = extract_pending_action(runtime_result)

        self.assertIsNotNone(pending_action)
        self.assertEqual(pending_action["input_data"]["remind_before_minutes"], 60)
        self.assertTrue(pending_action["input_data"]["_suppress_auto_reminder"])

    def test_google_calendar_embedded_reminder_skips_local_continuation(self):
        """Check Google Calendar reminder override does not run a duplicate local reminder."""
        pending_action = {
            "ability": "calendar",
            "action": "create",
            "input_data": {
                "action": "create",
                "remind_before_minutes": 60,
                "_suppress_auto_reminder": True,
            },
        }
        calendar_result = CalendarResult(
            success=True,
            action="create",
            provider="google",
            events=[
                CalendarEvent(
                    id="google-1",
                    title="meeting",
                    date="2099-07-19",
                    time="14:00",
                    reminder_minutes=[60],
                )
            ],
        )
        tool_result = SimpleNamespace(output=AbilityResult(success=True, data=calendar_result))

        self.assertTrue(should_skip_embedded_google_calendar_reminder_continuation(pending_action, tool_result))

    def test_calendar_conversation_task_collects_missing_fields_and_confirms(self):
        """Check Calendar conversation task collects fields before one final confirmation."""
        provider = MockCalendarProvider(events=[])
        engine = CountingReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider, reminder_engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=[
                    "\u0033\uc2dc",
                    "\uc544\uc57c\uc640 \uc720\uc774",
                    "\ub86f\ub370\uc6d4\ub4dc\ubab0",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
        self.assertEqual(chat_service.messages, [])
        self.assertGreaterEqual(len(tts_provider.spoken), 5)
        self.assertIn("\uba87 \uc2dc", tts_provider.spoken[0])
        self.assertIn("\ub204\uad6c", tts_provider.spoken[1])
        self.assertIn("\uc7a5\uc18c", tts_provider.spoken[2])
        self.assertIn("\ub4f1\ub85d\ud560\uae4c\uc694", tts_provider.spoken[3])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, tomorrow)
        self.assertEqual(provider.events[0].time, "15:00")
        self.assertEqual(provider.events[0].title, "\uc57d\uc18d")
        self.assertEqual(provider.events[0].participants, ["\uc544\uc57c", "\uc720\uc774"])
        self.assertEqual(provider.events[0].location, "\ub86f\ub370\uc6d4\ub4dc\ubab0")
        self.assertEqual(engine.create_count, 1)
        self.assertIsNone(pipeline.conversation_session.get_conversation_task())

    def test_calendar_conversation_task_can_be_cancelled(self):
        """Check Calendar conversation task cancellation stops execution."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=["\ucde8\uc18c", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(provider.events, [])
        self.assertTrue(any("\ucde8\uc18c" in text for text in tts_provider.spoken))

    def test_calendar_conversation_task_survives_follow_up_stt_failure(self):
        """Check STT failure during collection keeps the Calendar task active."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544 \uc918",
                follow_ups=[
                    "\u0033\uc2dc",
                    "Speech recognition failed: ",
                    "\uc544\uc57c\uc640 \uc720\uc774",
                    "\ub86f\ub370\uc6d4\ub4dc\ubab0",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(chat_service.messages, [])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].participants, ["\uc544\uc57c", "\uc720\uc774"])
        self.assertTrue(any("\ub2e4\uc2dc \ud55c \ubc88" in text for text in tts_provider.spoken))

    def test_calendar_conversation_task_final_confirmation_can_request_reminder(self):
        """Check final confirmation text can request and announce a reminder."""
        provider = MockCalendarProvider(events=[])
        engine = CountingReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider, reminder_engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544 \uc918",
                follow_ups=[
                    "\u0033\uc2dc",
                    "\uc544\uc57c\uc640 \uc720\uc774",
                    "\uc11c\uc6b8",
                    "\ub4f1\ub85d\ud574 \uc8fc\uace0 1\uc2dc\uac04 \uc804\uc5d0 \uc54c\ub824 \uc918",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(engine.create_count, 1)
        self.assertEqual(engine.list(state="pending")[0].remind_before, 60)
        self.assertTrue(any("\u0031\uc2dc\uac04 \uc804 \uc54c\ub9bc\ub3c4 \uc124\uc815\ud588\uc2b5\ub2c8\ub2e4" in text for text in tts_provider.spoken))

    def test_calendar_conversation_task_accepts_date_correction(self):
        """Check a follow-up correction updates date before execution."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=[
                    "\u0033\uc2dc",
                    "\uc544\ub2c8 \ub0b4\uc77c \ub9d0\uace0 \ubaa8\ub808",
                    "\uc544\uc57c\uc640 \uc720\uc774",
                    "\ub86f\ub370\uc6d4\ub4dc\ubab0",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        day_after_tomorrow = (datetime.now() + timedelta(days=2)).date().isoformat()
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, day_after_tomorrow)
        self.assertEqual(provider.events[0].participants, ["\uc544\uc57c", "\uc720\uc774"])
        self.assertEqual(provider.events[0].location, "\ub86f\ub370\uc6d4\ub4dc\ubab0")

    def test_calendar_conversation_task_reclassifies_non_person_participant_as_title(self):
        """Check non-person answers to participant questions become the event title."""
        provider = MockCalendarProvider(events=[])
        engine = CountingReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider, reminder_engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=[
                    "\uc624\uc804 10\uc2dc",
                    "\uc2e4\uc5c5 \uae09\uc5ec",
                    "\uace0\uc6a9\ubcf4\ud5d8\uacf5\ub2e8",
                    "\ub4f1\ub85d\ud574 \uc8fc\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824 \uc918",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].time, "10:00")
        self.assertEqual(provider.events[0].title, "\uc2e4\uc5c5\uae09\uc5ec")
        self.assertEqual(provider.events[0].participants, [])
        self.assertEqual(provider.events[0].location, "\uace0\uc6a9\ubcf4\ud5d8\uacf5\ub2e8")
        self.assertEqual(engine.create_count, 1)
        self.assertEqual(engine.list(state="pending")[0].remind_before, 30)
        self.assertTrue(any("\uc2e4\uc5c5\uae09\uc5ec \uc77c\uc815\uc73c\ub85c \ub4f1\ub85d\ud560\uae4c\uc694" in text for text in tts_provider.spoken))
        self.assertFalse(any("\uc2e4\uc5c5 \uae09\uc5ec \ub9cc\ub098\ub294" in text for text in tts_provider.spoken))

    def test_calendar_conversation_task_can_skip_optional_participants_and_location(self):
        """Check optional participant and location slots can be intentionally skipped."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=[
                    "\u0033\uc2dc",
                    "\ud63c\uc790",
                    "\uc7a5\uc18c\ub294 \uc544\uc9c1 \ubab0\ub77c",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].title, "\uc57d\uc18d")
        self.assertEqual(provider.events[0].participants, [])
        self.assertEqual(provider.events[0].location, "")

    def test_calendar_conversation_task_does_not_use_command_as_title_and_parses_day_only_date(self):
        """Check command-only create text keeps title missing and parses day-only dates."""
        today = datetime.now().date()
        if today.day >= 28:
            self.skipTest("day-only future date check needs a future day in the current month")
        day_only_target = today.replace(day=today.day + 1)
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=[
                    f"{day_only_target.day}\uc77c \uc624\uc804 10\uc2dc",
                    "\uc2e4\uc5c5 \uae09\uc5ec",
                    "\uc798 \ubab0\ub77c",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertGreaterEqual(len(tts_provider.spoken), 4)
        self.assertIn("\uc5b4\ub5a4 \uc77c\uc815", tts_provider.spoken[1])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, day_only_target.isoformat())
        self.assertEqual(provider.events[0].time, "10:00")
        self.assertEqual(provider.events[0].title, "\uc2e4\uc5c5\uae09\uc5ec")
        self.assertEqual(provider.events[0].participants, [])
        self.assertEqual(provider.events[0].location, "")
        self.assertNotEqual(provider.events[0].title, "\ub4f1\ub85d\ud574")

    def test_calendar_conversation_task_accepts_confirmation_title_correction(self):
        """Check confirmation-stage corrections can update the collected title."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=[
                    "\u0033\uc2dc",
                    "\uc544\uc57c\uc640 \uc720\uc774",
                    "\uc11c\uc6b8",
                    "\uc544\ub2c8, \ubcd1\uc6d0 \uc9c4\ub8cc\ub85c \ubc14\uafd4\uc918",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].title, "\ubcd1\uc6d0\uc9c4\ub8cc")
        self.assertEqual(provider.events[0].participants, [])

    def test_calendar_conversation_task_confirms_past_day_only_date_before_next_month(self):
        """Check past day-only dates ask before rolling to next month."""
        today_value = datetime.now().date()

        if today_value.day == 1:
            self.skipTest("day-only past-date test needs a current day after the 1st")

        past_day = today_value.day - 1
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=[
                    f"{past_day}\uc77c \uc624\uc804 10\uc2dc",
                    "\uc751",
                    "\uc2e4\uc5c5 \uae09\uc5ec",
                    "\uc798 \ubab0\ub77c",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        next_month = today_value.month + 1
        next_year = today_value.year

        if next_month > 12:
            next_month = 1
            next_year += 1

        self.assertTrue(any("\uc774\ubbf8 \uc9c0\ub0ac\uc2b5\ub2c8\ub2e4" in text for text in tts_provider.spoken))
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, datetime(next_year, next_month, past_day).date().isoformat())
        self.assertEqual(provider.events[0].time, "10:00")

    def test_calendar_conversation_task_replaces_rejected_past_date_candidate(self):
        """Check 'no + replacement date/time' updates instead of cancelling."""
        today_value = datetime.now().date()

        if today_value.day <= 1 or today_value.day >= 28:
            self.skipTest("past-date replacement test needs a safe replacement day in the current month")

        past_day = today_value.day - 1
        replacement_day = today_value.day + 2
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc77c\uc815 \uc7a1\uc544 \uc918",
                follow_ups=[
                    f"{past_day}\uc77c 12\uc2dc",
                    f"\uc544\ub2c8 {replacement_day}\uc77c 2\uc2dc",
                    "\uc2e4\uc5c5 \uae09\uc5ec",
                    "\uc7a5\uc18c\ub294 \uc544\uc9c1 \ubab0\ub77c",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, today_value.replace(day=replacement_day).isoformat())
        self.assertEqual(provider.events[0].time, "14:00")
        self.assertEqual(provider.events[0].title, "\uc2e4\uc5c5\uae09\uc5ec")

    def test_calendar_conversation_task_rejects_past_date_candidate_without_cancelling(self):
        """Check bare 'no' rejects the date candidate but keeps the task alive."""
        from jarvis.runtime.conversation_task import start_calendar_conversation_task, update_calendar_conversation_task

        today_value = datetime.now().date()

        if today_value.day <= 1:
            self.skipTest("past-date rejection test needs a current day after the 1st")

        past_day = today_value.day - 1
        task = start_calendar_conversation_task("\uc77c\uc815 \ub4f1\ub85d\ud574")

        reply = update_calendar_conversation_task(task, f"{past_day}\uc77c 12\uc2dc")
        self.assertIn("\uc774\ubbf8 \uc9c0\ub0ac\uc2b5\ub2c8\ub2e4", reply)

        reply = update_calendar_conversation_task(task, "\uc544\ub2c8")

        self.assertEqual(task.task_state, "active")
        self.assertEqual(task.state, "WAITING_CLARIFICATION")
        self.assertEqual(task.pending_clarification, "date")
        self.assertEqual(task.pending_date_candidate, "")
        self.assertIn("\uc5b8\uc81c", reply)

    def test_calendar_conversation_task_updates_title_from_not_this_but_that_phrase(self):
        """Check 'A 아니고 B로 바꿔줘' replaces the title, not the whole task."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=[
                    "\ub0b4\uc77c \uc624\uc804 10\uc2dc",
                    "\uc2e4\uc5c5 \uae09\uc5ec",
                    "\uc7a5\uc18c\ub294 \uc544\uc9c1 \ubab0\ub77c",
                    "\uc2e4\uc5c5\uae09\uc5ec \uc544\ub2c8\uace0 \ubcd1\uc6d0 \uc9c4\ub8cc\ub85c \ubc14\uafd4\uc918",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].title, "\ubcd1\uc6d0\uc9c4\ub8cc")
        self.assertEqual(provider.events[0].participants, [])

    def test_calendar_conversation_task_updates_date_and_time_from_not_this_but_that_phrase(self):
        """Check date/time replacement during confirmation updates the existing task."""
        today_value = datetime.now().date()

        if today_value.day >= 17:
            self.skipTest("date replacement test expects the 16th and 17th to be future dates this month")

        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=[
                    "\u0031\u0036\uc77c \uc624\uc804 10\uc2dc",
                    "\uc2e4\uc5c5 \uae09\uc5ec",
                    "\uc7a5\uc18c\ub294 \uc544\uc9c1 \ubab0\ub77c",
                    "\u0031\u0036\uc77c \ub9d0\uace0 \u0031\u0037\uc77c \uc624\ud6c4 2\uc2dc\ub85c \ubc14\uafd4\uc918",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].date, today_value.replace(day=17).isoformat())
        self.assertEqual(provider.events[0].time, "14:00")

    def test_calendar_conversation_task_skips_location_and_confirms_with_register_phrase(self):
        """Check optional location can be skipped and 'just register it' confirms."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=["\u0033\uc2dc", "\ud63c\uc790", "\uc7a5\uc18c\ub294 \uc5c6\uc5b4", "\uadf8\ub0e5 \ub4f1\ub85d\ud574", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].location, "")
        self.assertEqual(provider.events[0].participants, [])

    def test_calendar_conversation_task_is_saved_to_task_history(self):
        """Check completed conversation calendar tasks leave a RuntimeTask history snapshot."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        dispatcher = RuntimeToolDispatcher(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=dispatcher)
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918",
                follow_ups=["\u0033\uc2dc", "\ud63c\uc790", "\uc7a5\uc18c\ub294 \uc544\uc9c1 \ubab0\ub77c", "\uc751", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        latest = dispatcher.task_history.latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.status.value, "SUCCESS")
        self.assertEqual(latest.step_records[0].tool_name, "calendar")

    def test_calendar_conversation_task_expires_in_session(self):
        """Check expired conversation task is cleared by the session."""
        from jarvis.runtime.conversation_task import start_calendar_conversation_task

        session = create_conversation_session(follow_up_timeout=8)
        task = start_calendar_conversation_task("\ub0b4\uc77c \uc57d\uc18d \uc7a1\uc544\uc918")
        task.expires_turns = 0
        session.set_conversation_task(task)

        expired = session.get_conversation_task()

        self.assertIsNotNone(expired)
        self.assertEqual(getattr(expired, "task_state", ""), "expired")
        self.assertIsNone(session.conversation_task)

    def test_explicit_plan_reminder_suppresses_calendar_auto_reminder(self):
        """Check explicit Reminder step prevents duplicate Calendar auto-reminder creation."""
        provider = MockCalendarProvider(events=[])
        engine = CountingReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider, reminder_engine=engine))
        ability_registry.register(ReminderAbility(engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c 3\uc2dc\uc5d0 \uc57d\uc18d \uc7a1\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub824 \uc918",
                follow_ups=["\uc751 \ub4f1\ub85d\ud574", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(engine.create_count, 1)
        self.assertEqual(len(engine.list(state="pending")), 1)

    def test_intent_clarification_does_not_fall_through_to_legacy_runtime(self):
        """Check failed structured intent plans stop before legacy calendar fallback."""

        class ClarifyingIntentParser:
            def parse(self, text, context):
                return IntentParseResult(
                    success=False,
                    requires_clarification=True,
                    clarification_question="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc57d\uc18d\uc744 \ub4f1\ub85d\ud558\uace0 30\ubd84 \uc804\uc5d0 \uc54c\ub9bc\uc744 \uc124\uc815\ud560\uae4c\uc694?",
                    raw_text=text,
                    normalized_text=text,
                    source="ai",
                    confidence=0.86,
                )

        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry, intent_parser=ClarifyingIntentParser()))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc77c\uc815 \ub4f1\ub85d\ud574\uc918",
                follow_ups=[],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=0,
        )

        reply = pipeline.process_voice_turn()

        self.assertEqual(chat_service.messages, [])
        self.assertEqual(provider.events, [])
        self.assertNotEqual(reply, "\ub0b4\uc77c\uc740 \uc77c\uc815\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.")
        self.assertIn("\uc124\uc815\ud560\uae4c\uc694", reply)

    def test_confirmation_decision_accepts_compound_yes_reply(self):
        """Check natural short confirmation phrases are accepted."""
        self.assertEqual(confirmation_decision("\uc751"), "yes")
        self.assertEqual(confirmation_decision("\uc6c5"), "yes")
        self.assertEqual(confirmation_decision("\uc74c"), "yes")
        self.assertEqual(confirmation_decision("\uc5b4"), "yes")
        self.assertEqual(confirmation_decision("\ub135"), "yes")
        self.assertEqual(confirmation_decision("\uc751 \ub4f1\ub85d\ud574"), "yes")
        self.assertEqual(confirmation_decision("\uc751 \ub4f1\ub85d\ud574 \uc918"), "yes")
        self.assertEqual(confirmation_decision("\uc9c4\ud589\ud574"), "yes")
        self.assertEqual(confirmation_decision("\uc2b9\uc778"), "yes")
        self.assertEqual(confirmation_decision("Gr\u00f6nn"), "yes")
        self.assertEqual(confirmation_decision("\uc544\ub2c8\uc57c"), "no")
        self.assertEqual(confirmation_decision("\ubcf4\ub958"), "no")

    def test_calendar_confirmation_decision_accepts_short_yes_variants(self):
        """Check Calendar conversation final confirmation accepts short variants."""
        self.assertEqual(calendar_confirmation_decision("\uc751"), "yes")
        self.assertEqual(calendar_confirmation_decision("\uc6c5"), "yes")
        self.assertEqual(calendar_confirmation_decision("\uc74c"), "yes")
        self.assertEqual(calendar_confirmation_decision("\ub135"), "yes")
        self.assertEqual(calendar_confirmation_decision("Gr\u00f6nn"), "yes")

    def test_meeting_create_without_person_starts_calendar_conversation(self):
        """Check dropped person names in meeting phrases cause a clarification."""
        self.assertTrue(
            should_start_calendar_conversation(
                "\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574"
            )
        )

    def test_alarm_like_unhandled_request_does_not_use_llm_fake_success(self):
        """Check alarm-like failures return a safe prompt instead of LLM success."""
        chat_service = CapturingChatService()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\u0031\ubd84 \ub4a4\uc5d0 \ubb3c \ub9c8\uc2dc\uac8c \uc54c\ub78c \ub4f1\ub85d\ud574",
                follow_ups=[],
            ),
            chat_service=chat_service,
            tts_provider=CapturingTTSProvider(),
            intent_runtime=IntentRuntime(tool_dispatcher=ToolDispatcher(ToolRegistry())),
            follow_up_timeout=0,
        )

        reply = pipeline.process_voice_turn()

        self.assertEqual(chat_service.messages, [])
        self.assertEqual(reply, "\uc54c\ub9bc \uc2dc\uac04\uc744 \ub2e4\uc2dc \ub9d0\uc500\ud574 \uc8fc\uc138\uc694.")

    def test_pending_reminder_clarification_preserves_original_title(self):
        """Check a follow-up delay completes the original ambiguous reminder."""
        engine = ReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(ReminderAbility(engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\uc870\uae08 \uc774\ub530\uac00 \ubb3c \ub9c8\uc2dc\ub77c\uace0 \uc54c\ub824 \uc918",
                follow_ups=["\u0031\ubd84 \ub4a4\uc5d0 \uc54c\ub824 \uc918", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        reminders = engine.list(state="pending")
        self.assertEqual(chat_service.messages, [])
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].title, "\ubb3c \ub9c8\uc2dc\uae30")
        self.assertEqual(reminders[0].remind_before, 0)

    def test_calendar_created_event_follow_up_creates_reminder(self):
        """Check '30분 전에 알려줘' attaches to the last created Calendar event."""
        provider = MockCalendarProvider(events=[])
        engine = ReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register(ReminderAbility(engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        chat_service = CapturingChatService()
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=["\uc751", "\u0033\u0030\ubd84 \uc804\uc5d0 \uc54c\ub824 \uc918", ""],
            ),
            chat_service=chat_service,
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        reminders = engine.list(state="pending")
        self.assertEqual(chat_service.messages, [])
        self.assertEqual(len(provider.events), 1)
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].remind_before, 30)
        self.assertEqual(reminders[0].title, provider.events[0].title)
        self.assertIn("\uc54c\ub9bc\uc744 \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4", tts_provider.spoken[-1])


    def test_calendar_created_event_can_be_updated_by_relative_followups(self):
        """Check the last Calendar event can be patched through consecutive follow-ups."""
        provider = MockCalendarProvider(events=[])
        engine = ReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider, reminder_engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=[
                    "\uc751",
                    "4\uc2dc\ub85c \ubc14\uafd4",
                    "\uc751",
                    "\uc11c\uc6b8\uc5ed\uc73c\ub85c \ubcc0\uacbd",
                    "\uc751",
                    "\uc720\uc774\ub3c4 \ucd94\uac00",
                    "\uc751",
                    "",
                ],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].time, "16:00")
        self.assertEqual(provider.events[0].location, "\uc11c\uc6b8\uc5ed")
        self.assertEqual(provider.events[0].participants, ["\uc544\uc57c", "\uc720\uc774"])
        self.assertEqual(len(engine.list(state="pending")), 1)
        self.assertEqual(engine.list(state="pending")[0].trigger_time, f"{provider.events[0].date}T15:30:00")

    def test_calendar_conversation_meeting_confirmation_avoids_duplicate_meeting_title(self):
        """Check generic meeting titles do not duplicate the participant phrase."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        tts_provider = CapturingTTSProvider()
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=["\uc544\uc57c", "\uc7a0\uc2e4", "\uc751", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=tts_provider,
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].title, "\uc544\uc57c \ub9cc\ub098\uae30")
        self.assertEqual(provider.events[0].participants, ["\uc544\uc57c"])
        self.assertEqual(provider.events[0].location, "\uc7a0\uc2e4")
        self.assertTrue(any("\uc7a0\uc2e4\uc5d0\uc11c \uc544\uc57c\uc640 \ub9cc\ub098\ub294 \uc77c\uc815\uc73c\ub85c \ub4f1\ub85d\ud560\uae4c\uc694" in text for text in tts_provider.spoken))
        self.assertFalse(any("\ub9cc\ub098\ub294 \ub9cc\ub098\uae30" in text for text in tts_provider.spoken))

    def test_calendar_conversation_final_confirmation_uses_confirmation_listener(self):
        """Check Calendar final confirmation listens with short-answer timing."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=RuntimeToolDispatcher(tool_registry))
        stt_provider = ConfirmationAwareSTTProvider(
            first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
            follow_ups=["\uc544\uc57c", "\uc7a0\uc2e4", "\uc751", ""],
        )
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=stt_provider,
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertGreaterEqual(stt_provider.confirmation_calls, 1)
        self.assertEqual(len(provider.events), 1)

    def test_calendar_relative_update_uses_runtime_event_after_new_wake_session(self):
        """Check a new wake session can still patch the last created Calendar event."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=["\uc751", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()
        self.assertEqual(len(provider.events), 1)

        pipeline.stt_provider = FollowUpSTTProvider(
            first="\uadf8 \uc77c\uc815 \uc11c\uc6b8\uc5ed\uc73c\ub85c \ubc14\uafd4",
            follow_ups=["\uc751", ""],
        )
        pipeline.run_once()

        self.assertEqual(len(provider.events), 1)
        self.assertEqual(provider.events[0].location, "\uc11c\uc6b8\uc5ed")

    def test_calendar_relative_update_treats_seoul_station_alias_as_location(self):
        """Check a Seoul Station STT alias updates location, not title."""
        provider = MockCalendarProvider(events=[])
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=["\uc751", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()
        pipeline.stt_provider = FollowUpSTTProvider(
            first="\uadf8 \uc77c\uc815 \uc124\ub9bd\uc73c\ub85c \ubc14\uafd4",
            follow_ups=["\uc751", ""],
        )
        pipeline.run_once()

        self.assertEqual(provider.events[0].location, "\uc11c\uc6b8\uc5ed")
        self.assertEqual(provider.events[0].title, "\uc544\uc57c \ub9cc\ub098\uae30")

    def test_calendar_created_event_can_be_deleted_by_relative_followup(self):
        """Check the last Calendar event can be deleted by relative reference."""
        provider = MockCalendarProvider(events=[])
        engine = ReminderEngine(queue=ReminderQueue())
        tool_registry = ToolRegistry()
        ability_registry = AbilityRegistry()
        ability_registry.register(CalendarAbility(provider=provider, reminder_engine=engine))
        ability_registry.register_tools(tool_registry)
        runtime = IntentRuntime(tool_dispatcher=ToolDispatcher(tool_registry))
        pipeline = VoicePipeline(
            wake_listener=CountingWakeListener(),
            stt_provider=FollowUpSTTProvider(
                first="\ub0b4\uc77c \uc624\ud6c4 3\uc2dc\uc5d0 \uc544\uc57c \ub9cc\ub098\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574",
                follow_ups=["\uc751", "\uadf8 \uc77c\uc815 \uc0ad\uc81c\ud574", "\uc751", ""],
            ),
            chat_service=CapturingChatService(),
            tts_provider=CapturingTTSProvider(),
            intent_runtime=runtime,
            follow_up_timeout=8,
        )

        pipeline.run_once()

        self.assertEqual(provider.events, [])
        self.assertEqual(len(engine.list(state="pending")), 0)


class CountingWakeListener:
    """Wake listener test double."""

    def __init__(self):
        """Create wake listener state."""
        self.calls = 0

    def wait_for_wake_word(self):
        """Count wake-word waits."""
        self.calls += 1


class CountingReminderEngine(ReminderEngine):
    """ReminderEngine test double that counts create calls."""

    def __init__(self, *args, **kwargs):
        """Create counting engine."""
        super().__init__(*args, **kwargs)
        self.create_count = 0

    def create(self, *args, **kwargs):
        """Count create calls."""
        self.create_count += 1
        return super().create(*args, **kwargs)


class FollowUpMailProvider:
    def __init__(self):
        self.messages = (
            MailMessage(
                id="mail-1",
                thread_id="thread-1",
                sender_name="아야,",
                sender_email="aya@example.com",
                subject="일정 확인",
                body_summary="테스트 본문",
                rfc_message_id="<mail-1@example.com>",
            ),
        )
        self.reply_calls = 0

    def list_messages(self, query):
        return MailResult(success=True, action="list", messages=self.messages, message_count=1)

    def search_messages(self, query):
        return MailResult(success=True, action="search", messages=self.messages, message_count=1)

    def get_message(self, message_id):
        message = self.messages[0] if message_id == self.messages[0].id else None
        return MailResult(
            success=message is not None,
            action="get",
            message=message,
            messages=(message,) if message else (),
            message_count=1 if message else 0,
            error_code="" if message else "MAIL_NOT_FOUND",
        )

    def reply_message(self, outgoing):
        self.reply_calls += 1
        raise AssertionError("Reply must not run after cancellation.")


class FollowUpSTTProvider:
    """STT test double with follow-up support."""

    def __init__(self, first, follow_ups):
        """Create scripted STT output."""
        self.first = first
        self.follow_ups = list(follow_ups)

    def listen(self):
        """Return initial input."""
        return self.first

    def listen_for_follow_up(self, timeout):
        """Return the next follow-up input."""
        if len(self.follow_ups) == 0:
            return ""

        return self.follow_ups.pop(0)


class ConfirmationAwareSTTProvider(FollowUpSTTProvider):
    """STT test double that records confirmation-mode listens."""

    def __init__(self, first, follow_ups):
        """Create scripted STT output with confirmation tracking."""
        super().__init__(first, follow_ups)
        self.confirmation_calls = 0

    def listen_for_confirmation(self, timeout=None):
        """Return the next follow-up input and count confirmation listens."""
        self.confirmation_calls += 1
        return self.listen_for_follow_up(timeout)


class CapturingChatService:
    """Chat service test double."""

    provider = object()

    def __init__(self):
        """Create chat capture."""
        self.messages = []

    def generate_reply(self, message):
        """Record message and return deterministic reply."""
        self.messages.append(message)
        return f"reply: {message}"


class CapturingTTSProvider:
    """TTS test double."""

    streaming_enabled = False

    def __init__(self):
        """Create TTS capture."""
        self.spoken = []

    def speak(self, text):
        """Capture spoken text."""
        self.spoken.append(text)


if __name__ == "__main__":
    unittest.main()
