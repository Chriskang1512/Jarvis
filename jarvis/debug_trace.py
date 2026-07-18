import json
import logging
import os
from pathlib import Path


LOGGER = logging.getLogger("jarvis.trace")


def is_debug_trace_enabled():
    """Return whether detailed runtime trace logging is enabled."""
    return read_debug_trace_value().lower() in ["1", "true", "yes", "on"]


def trace_event(event, **payload):
    """Log a structured debug trace event when enabled."""
    if not is_debug_trace_enabled():
        return

    message = format_trace_event(event, payload)

    if message is not None:
        print(message, flush=True)
        LOGGER.debug(message)

    if is_raw_trace_enabled():
        raw_message = f"TRACE {event} {json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)}"
        print(raw_message, flush=True)
        LOGGER.debug(raw_message)


def format_trace_event(event, payload):
    """Return a human-readable trace line."""
    if event == "weather.query":
        return (
            "[Weather] query "
            f"location={payload.get('location')} "
            f"date={payload.get('date')} "
            f"mode={payload.get('mode')} "
            f"capability={payload.get('capability')} "
            f"confidence={payload.get('confidence')}"
        )

    if event == "weather.provider":
        fallback = "YES" if payload.get("fallback_used") else "NO"
        reason = payload.get("fallback_reason") or "-"
        return (
            "[Weather] provider "
            f"requested={payload.get('provider_requested')} "
            f"used={payload.get('provider_used')} "
            f"fallback={fallback} "
            f"reason={reason} "
            f"key_loaded={yes_no(payload.get('api_key_loaded'))} "
            f"location={payload.get('location')} "
            f"resolved={payload.get('resolved_location', '-')} "
            f"endpoint={payload.get('endpoint')}"
        )

    if event == "weather.result":
        return (
            "[Weather] result "
            f"success={yes_no(payload.get('success'))} "
            f"provider={payload.get('provider_used')} "
            f"location={payload.get('location')} "
            f"mode={payload.get('mode')}"
        )

    if event == "google_auth.status":
        return (
            "[GoogleAuth] "
            f"credential_state={payload.get('status') or '-'} "
            f"scopes={payload.get('scopes') or '-'}"
        )

    if event == "google_calendar.request":
        return (
            "[GoogleCalendar] request "
            f"action={payload.get('action') or '-'} "
            f"provider={payload.get('provider') or 'google'}"
        )

    if event == "google_calendar.response":
        return (
            "[GoogleCalendar] response "
            f"events={payload.get('events', 0)} "
            f"provider={payload.get('provider') or 'google'}"
        )

    if event == "memory.query":
        if not is_memory_verbose_trace_enabled():
            return None

        return (
            "[Memory] query "
            f"action={payload.get('action')} "
            f"key={payload.get('key')} "
            f"scope={payload.get('scope')} "
            f"category={payload.get('category')} "
            f"confidence={payload.get('confidence')}"
        )

    if event == "memory.summary":
        return (
            "[Memory] "
            f"intent={payload.get('intent')} "
            f"entity={payload.get('entity') or '-'} "
            f"attribute={payload.get('attribute') or '-'} "
            f"canonical_key={payload.get('canonical_key') or '-'} "
            f"source={payload.get('source') or '-'} "
            f"found={yes_no(payload.get('found'))} "
            f"value={payload.get('value') or '-'} "
            f"duration={payload.get('duration_ms', 0)}ms"
        )

    if event == "memory.store":
        if not is_memory_verbose_trace_enabled():
            return None

        return (
            "[Memory] store "
            f"action={payload.get('action')} "
            f"key={payload.get('key')} "
            f"scope={payload.get('scope')} "
            f"storage={payload.get('storage')} "
            f"deleted={payload.get('deleted', '-')}"
        )

    if event == "memory.storage":
        if not is_memory_verbose_trace_enabled():
            return None

        return (
            "[Memory] storage "
            f"provider={payload.get('provider')} "
            f"entries={payload.get('entries')} "
            f"path={payload.get('path')}"
        )

    if event == "memory.result":
        if not is_memory_verbose_trace_enabled():
            return None

        return (
            "[Memory] result "
            f"success={yes_no(payload.get('success'))} "
            f"action={payload.get('action')} "
            f"key={payload.get('key')} "
            f"found={yes_no(payload.get('found'))} "
            f"entries={payload.get('entries')}"
        )

    if event == "memory.date_elapsed":
        return (
            "[Memory] date_elapsed "
            f"key={payload.get('key')} "
            f"start_date={payload.get('start_date')} "
            f"current_date={payload.get('current_date')} "
            f"elapsed_days={payload.get('elapsed_days')}"
        )

    if event == "memory.elapsed_intent":
        return (
            "[Memory] elapsed_intent "
            f"matched={yes_no(payload.get('matched'))} "
            f"source={payload.get('source') or '-'}"
        )

    if event == "memory.canonical_key":
        if not is_memory_verbose_trace_enabled():
            return None

        return (
            "[Memory] canonical_key "
            f"source_text=\"{payload.get('source_text')}\" "
            f"canonical_key={payload.get('canonical_key') or '-'}"
        )

    if event == "memory.legacy_key_fallback":
        if not is_memory_verbose_trace_enabled():
            return None

        return (
            "[Memory] legacy_key_fallback "
            f"legacy_key={payload.get('legacy_key')} "
            f"canonical_key={payload.get('canonical_key')}"
        )

    if event == "contact.matched":
        return (
            "[Contact] matched "
            f"query={payload.get('query') or '-'} "
            f"id={payload.get('id') or '-'} "
            f"name={payload.get('name') or '-'}"
        )

    if event == "contact.miss":
        return f"[Contact] miss query={payload.get('query') or '-'}"

    if event == "contact.query":
        return (
            "[Contact] query "
            f"action={payload.get('action') or '-'} "
            f"id={payload.get('contact_id') or '-'} "
            f"name={payload.get('display_name') or '-'} "
            f"attribute={payload.get('attribute') or '-'}"
        )

    if event == "contact.permission":
        return (
            "[Contact] permission "
            f"action={payload.get('action') or '-'} "
            f"permission={payload.get('permission') or '-'}"
        )

    if event == "contact.result":
        return (
            "[Contact] result "
            f"action={payload.get('action') or '-'} "
            f"id={payload.get('contact_id') or '-'} "
            f"success={yes_no(payload.get('success'))} "
            f"error={payload.get('error_code') or '-'} "
            f"provider={payload.get('provider') or '-'} "
            f"duration={payload.get('execution_time_ms', 0)}ms "
            f"correlation={payload.get('correlation_id') or '-'}"
        )

    if event == "contact.created":
        return (
            "[Contact] created "
            f"id={payload.get('id') or '-'} "
            f"name={payload.get('name') or '-'}"
        )

    if event == "contact.updated":
        return (
            "[Contact] updated "
            f"id={payload.get('id') or '-'} "
            f"name={payload.get('name') or '-'} "
            f"fields={payload.get('fields') or '-'}"
        )

    if event == "contact.deleted":
        return (
            "[Contact] deleted "
            f"id={payload.get('id') or '-'} "
            f"name={payload.get('name') or '-'}"
        )

    if event == "contact.event":
        return (
            "[Contact] event="
            f"{payload.get('event_type') or '-'} "
            f"event_id={payload.get('event_id') or '-'} "
            f"id={payload.get('id') or '-'} "
            f"revision={payload.get('revision') or '-'} "
            f"changed={payload.get('changed') or '-'} "
            f"source={payload.get('source') or '-'} "
            f"confidence={payload.get('confidence', '-')} "
            f"correlation={payload.get('correlation_id') or '-'}"
        )

    if event == "contact.metrics":
        return (
            "[Contact] metrics "
            f"hit={payload.get('contact_hit', 0)} "
            f"miss={payload.get('contact_miss', 0)} "
            f"created={payload.get('contact_created', 0)} "
            f"updated={payload.get('contact_updated', 0)} "
            f"deleted={payload.get('contact_deleted', 0)} "
            f"merged={payload.get('contact_merged', 0)} "
            f"restored={payload.get('contact_restored', 0)} "
            f"events={payload.get('event_count', 0)} "
            f"revisions={payload.get('revision_count', 0)} "
            f"history={payload.get('history_size', 0)}"
        )

    if event == "event.publish":
        return (
            "[Event] publish "
            f"{payload.get('event_type') or '-'} "
            f"event_id={payload.get('event_id') or '-'} "
            f"aggregate={payload.get('aggregate_id') or '-'} "
            f"trace={payload.get('trace_id') or '-'} "
            f"correlation={payload.get('correlation_id') or '-'} "
            f"causation={payload.get('causation_id') or '-'}"
        )

    if event == "event.handler":
        return (
            "[Event] handler "
            f"{payload.get('handler') or '-'} "
            f"event={payload.get('event_type') or '-'} "
            f"event_id={payload.get('event_id') or '-'} "
            f"success={yes_no(payload.get('success'))} "
            f"attempt={payload.get('attempt') or '-'} "
            f"latency={payload.get('latency_ms', 0)}ms "
            f"error={payload.get('error') or '-'}"
        )

    if event == "event.handler_retry":
        return (
            "[Event] handler_retry "
            f"event_id={payload.get('event_id') or '-'} "
            f"handler={payload.get('handler') or '-'} "
            f"attempt={payload.get('attempt') or '-'}/{payload.get('max_attempts') or '-'} "
            f"error={payload.get('error') or '-'}"
        )

    if event == "event.completed":
        return (
            "[Event] completed "
            f"{payload.get('event_type') or '-'} "
            f"event_id={payload.get('event_id') or '-'} "
            f"handled={payload.get('handled', 0)} "
            f"failed={payload.get('failed', 0)} "
            f"duplicate={yes_no(payload.get('duplicate'))} "
            f"latency={payload.get('latency_ms', 0)}ms"
        )

    if event == "todo.query":
        return (
            "[Todo] query "
            f"action={payload.get('action') or '-'} "
            f"title={payload.get('title') or '-'} "
            f"due_at={payload.get('due_at') or '-'} "
            f"status={payload.get('status') or '-'}"
        )

    if event == "todo.permission":
        return (
            "[Todo] permission "
            f"action={payload.get('action') or '-'} "
            f"permission={payload.get('permission') or '-'}"
        )

    if event == "todo.result":
        return (
            "[Todo] result "
            f"action={payload.get('action') or '-'} "
            f"id={payload.get('todo_id') or '-'} "
            f"success={yes_no(payload.get('success'))} "
            f"error={payload.get('error_code') or '-'} "
            f"provider={payload.get('provider') or '-'} "
            f"duration={payload.get('execution_time_ms', 0)}ms"
        )

    if event == "todo.revision":
        return f"[Todo] revision id={payload.get('id') or '-'} revision={payload.get('revision') or '-'}"

    if event == "todo.completed":
        return f"[Todo] completed id={payload.get('id') or '-'} title={payload.get('title') or '-'}"

    if event == "todo.deleted":
        return f"[Todo] deleted id={payload.get('id') or '-'} title={payload.get('title') or '-'}"

    if event == "calendar.query":
        participants = payload.get("participants") or []
        participant_text = ",".join(str(participant) for participant in participants) or "-"
        return (
            "[Calendar] query "
            f"action={payload.get('action')} "
            f"date={payload.get('date')} "
            f"time={payload.get('time')} "
            f"title={payload.get('title') or '-'} "
            f"participants=[{participant_text}] "
            f"location={payload.get('location') or '-'}"
        )

    if event == "calendar.provider":
        return (
            "[Calendar] provider "
            f"action={payload.get('action')} "
            f"provider={payload.get('provider')}"
        )

    if event == "calendar.permission":
        return (
            "[Calendar] permission "
            f"action={payload.get('action')} "
            f"permission={payload.get('permission')}"
        )

    if event == "calendar.result":
        return (
            "[Calendar] result "
            f"action={payload.get('action')} "
            f"provider={payload.get('provider')} "
            f"events={payload.get('events')} "
            f"success={yes_no(payload.get('success'))}"
        )

    if event == "conversation.task":
        missing = payload.get("missing") or "-"
        return (
            "[Conversation] "
            f"task={payload.get('task_id') or '-'} "
            f"state={payload.get('state') or '-'} "
            f"task_state={payload.get('task_state') or '-'} "
            f"missing={missing} "
            f"turn={payload.get('turn', 0)}"
        )

    if event == "conversation.field_updated":
        value = payload.get("value")
        value_text = f" value={value}" if value not in [None, ""] else ""
        return (
            "[Conversation] "
            f"task={payload.get('task_id') or '-'} "
            f"field_updated={payload.get('field') or '-'}"
            f"{value_text}"
        )

    if event == "conversation.active_task_cleared":
        return (
            "[Conversation] "
            f"active_task cleared "
            f"task={payload.get('task_id') or '-'}"
        )

    if event == "conversation.retry":
        return (
            "[Conversation] retry "
            f"task={payload.get('task_id') or '-'} "
            f"state={payload.get('state') or '-'} "
            f"pending={payload.get('pending_clarification') or '-'} "
            f"reason={payload.get('reason') or '-'}"
        )

    if event in ["dispatcher.selected", "dispatcher.result"]:
        step_text = ""
        task_text = ""

        if payload.get("step_index", 0):
            step_text = f" step={payload.get('step_index')}/{payload.get('step_count')}"

        if payload.get("task_id"):
            task_text = f" task={payload.get('task_id')}"

        return (
            "[Dispatcher] "
            f"intent={payload.get('intent')} "
            f"selected={payload.get('selected')} "
            f"provider={payload.get('provider') or '-'} "
            f"success={yes_no(payload.get('success'))} "
            f"duration={payload.get('duration_ms', 0)}ms"
            f"{task_text}"
            f"{step_text}"
        )

    if event == "planner.parse":
        return f"[Planner] parse raw={payload.get('raw_text')}"

    if event == "planner.step":
        return (
            "[Planner] "
            f"step={payload.get('step_index')}/{payload.get('step_count')} "
            f"{payload.get('tool')}.{payload.get('action') or '-'}"
        )

    if event == "planner.completed":
        unsupported = payload.get("unsupported_reason") or ""
        unsupported_text = f" unsupported={unsupported}" if unsupported else ""
        return (
            "[Planner] completed "
            f"steps={payload.get('step_count')} "
            f"success={yes_no(payload.get('success'))}"
            f"{unsupported_text}"
        )

    if event == "planner.resume_after_confirmation":
        return (
            "[Planner] resume_after_confirmation "
            f"plan_id={payload.get('plan_id') or '-'} "
            f"steps={payload.get('step_count')}"
        )

    if event == "planner.executing_step":
        task_text = f" task={payload.get('task_id')}" if payload.get("task_id") else ""
        return (
            "[Planner] executing "
            f"step={payload.get('step_index')}/{payload.get('step_count')} "
            f"{payload.get('tool')}.{payload.get('action') or '-'}"
            f"{task_text}"
        )

    if event == "task.started":
        return (
            "[Task] started "
            f"id={payload.get('task_id')} "
            f"steps={payload.get('step_count')} "
            f"goal=\"{payload.get('goal')}\""
        )

    if event == "task.step.started":
        return (
            "[Task] step_started "
            f"id={payload.get('task_id')} "
            f"step={payload.get('step_index')}/{payload.get('step_count')} "
            f"{payload.get('tool')}.{payload.get('action') or '-'}"
        )

    if event == "task.step.completed":
        return (
            "[Task] step_completed "
            f"id={payload.get('task_id') or '-'} "
            f"step={payload.get('step_index')} "
            f"tool={payload.get('tool')} "
            f"attempts={payload.get('attempts')} "
            f"duration={payload.get('duration_ms', 0)}ms"
        )

    if event == "task.step.retry":
        return (
            "[Task] retry "
            f"id={payload.get('task_id') or '-'} "
            f"step={payload.get('step_index')} "
            f"tool={payload.get('tool')} "
            f"retry={payload.get('retry_count')}/{payload.get('max_retry')}"
        )

    if event == "task.step.failed":
        details = ""

        if payload.get("reason") or payload.get("validator") or payload.get("field"):
            details = (
                f" reason={payload.get('reason') or '-'}"
                f" validator={payload.get('validator') or '-'}"
                f" field={payload.get('field') or '-'}"
            )

        return (
            "[Task] step_failed "
            f"id={payload.get('task_id') or '-'} "
            f"step={payload.get('step_index')} "
            f"tool={payload.get('tool')} "
            f"attempts={payload.get('attempts')} "
            f"duration={payload.get('duration_ms', 0)}ms "
            f"error={payload.get('error') or '-'}"
            f"{details}"
        )

    if event == "task.completed":
        return (
            "[Task] completed "
            f"id={payload.get('task_id')} "
            f"status={payload.get('status')} "
            f"steps={payload.get('step_count')} "
            f"retries={payload.get('retry_count')} "
            f"duration={payload.get('duration_ms')}ms"
        )

    if event == "task.summary":
        return (
            "[Task] summary "
            f"id={payload.get('task_id')} "
            f"status={payload.get('status')} "
            f"steps={payload.get('step_count')} "
            f"retry={payload.get('retry_count')} "
            f"duration={payload.get('duration_ms')}ms"
        )

    if event == "intent.rule":
        return (
            "[Intent] rule "
            f"matched={yes_no(payload.get('matched'))} "
            f"confidence={payload.get('confidence')}"
        )

    if event == "intent.ai.requested":
        return f"[Intent] ai requested model={payload.get('model') or '-'}"

    if event == "intent.ai.parsed":
        return (
            "[Intent] ai parsed "
            f"ability={payload.get('ability') or '-'} "
            f"action={payload.get('action') or '-'} "
            f"confidence={payload.get('confidence')}"
        )

    if event == "intent.ai.failed":
        return (
            "[Intent] ai failed "
            f"latency={payload.get('latency_ms', 0)}ms "
            f"finish_reason={payload.get('finish_reason') or '-'} "
            f"error={truncate(str(payload.get('error') or '-'), 160)}"
        )

    if event == "intent.api_error":
        return (
            "[Intent] api_error "
            f"status={payload.get('status') or '-'} "
            f"error_type={payload.get('error_type') or '-'} "
            f"error_code={payload.get('error_code') or '-'} "
            f"error_param={payload.get('error_param') or '-'} "
            f"retry_profile={payload.get('retry_profile') or '-'} "
            f"message={truncate(str(payload.get('message') or '-'), 160)}"
        )

    if event == "intent.compatibility_retry":
        removed = payload.get("removed") or []
        return (
            "[Intent] compatibility_retry "
            f"model={payload.get('model') or '-'} "
            f"attempt={payload.get('attempt') or '-'} "
            f"removed=[{', '.join(removed)}] "
            f"retry_profile={payload.get('retry_profile') or '-'}"
        )

    if event == "intent.validation":
        return f"[Intent] validation success={yes_no(payload.get('success'))}"

    if event == "intent.selected":
        return f"[Intent] selected source={payload.get('source') or '-'}"

    if event == "intent.metrics":
        return (
            "[Intent] metrics "
            f"latency={payload.get('latency_ms', 0)}ms "
            f"input_tokens={payload.get('input_tokens', 0)} "
            f"output_tokens={payload.get('output_tokens', 0)} "
            f"intent_count={payload.get('intent_count', 0)} "
            f"finish_reason={payload.get('finish_reason') or '-'} "
            f"truncated={yes_no(payload.get('truncated'))} "
            f"source={payload.get('source') or '-'}"
        )

    if event == "intent.stats":
        return (
            "[Intent] stats "
            f"total={payload.get('total', 0)} "
            f"rule={payload.get('rule_hit_rate', 0)}% "
            f"ai={payload.get('ai_hit_rate', 0)}% "
            f"fallback={payload.get('fallback_rate', 0)}% "
            f"clarification={payload.get('clarification_rate', 0)}% "
            f"avg_confidence={payload.get('average_confidence', 0):.2f}"
        )

    if event == "integration.request":
        return (
            "[Integration] request "
            f"workflow={payload.get('workflow')} "
            f"action={payload.get('action')} "
            f"conversation={payload.get('conversation_id') or '-'} "
            f"session={payload.get('session_id') or '-'} "
            f"request={payload.get('request_id') or '-'} "
            f"workflow_id={payload.get('workflow_id') or '-'}"
        )

    if event == "integration.permission":
        return (
            "[Integration] permission "
            f"workflow={payload.get('workflow')} "
            f"permission={payload.get('permission')}"
        )

    if event == "integration.provider":
        return (
            "[Integration] provider "
            f"requested={payload.get('requested')} "
            f"used={payload.get('used')} "
            f"workflow={payload.get('workflow')}"
        )

    if event == "integration.response":
        return (
            "[Integration] response "
            f"status={payload.get('status')} "
            f"duration={payload.get('duration_ms', 0)}ms "
            f"workflow={payload.get('workflow')}"
        )

    if event == "integration.validation":
        return (
            "[Integration] validation "
            f"success={yes_no(payload.get('success'))} "
            f"workflow={payload.get('workflow')}"
        )

    if event == "integration.completed":
        return (
            "[Integration] completed "
            f"workflow={payload.get('workflow')} "
            f"success={yes_no(payload.get('success', True))} "
            f"duration={payload.get('duration_ms', 0)}ms "
            f"conversation={payload.get('conversation_id') or '-'} "
            f"request={payload.get('request_id') or '-'}"
        )

    if event == "integration.failed":
        return (
            "[Integration] failed "
            f"workflow={payload.get('workflow')} "
            f"error={payload.get('error_code')} "
            f"duration={payload.get('duration_ms', 0)}ms "
            f"conversation={payload.get('conversation_id') or '-'} "
            f"request={payload.get('request_id') or '-'}"
        )

    if event == "integration.metrics":
        return (
            "[Integration] metrics "
            f"provider={payload.get('provider')} "
            f"success={payload.get('success', 0)} "
            f"failed={payload.get('failed', 0)} "
            f"timeout={payload.get('timeout', 0)} "
            f"avg_latency={payload.get('average_latency_ms', 0)}ms"
        )

    if event == "reminder.query":
        return (
            "[Reminder] query "
            f"action={payload.get('action')} "
            f"title={payload.get('title') or '-'} "
            f"datetime={payload.get('datetime')} "
            f"remind_before={payload.get('remind_before')}m"
        )

    if event == "reminder.parser":
        return (
            "[Reminder] parser "
            f"raw={payload.get('raw')} "
            f"matched_pattern={payload.get('matched_pattern') or '-'} "
            f"time={payload.get('time') or '-'} "
            f"title={payload.get('title') or '-'}"
        )

    if event == "reminder.create":
        return (
            "[Reminder] create "
            f"id={payload.get('id')} "
            f"title={payload.get('title')} "
            f"datetime={payload.get('datetime')} "
            f"trigger_time={payload.get('trigger_time', '-')} "
            f"status={payload.get('status', '-')} "
            f"priority={payload.get('priority', '-')} "
            f"calendar_id={payload.get('calendar_id', '-')}"
        )

    if event == "reminder.update":
        return (
            "[Reminder] update "
            f"id={payload.get('id')} "
            f"source={payload.get('source')} "
            f"source_id={payload.get('source_id')}"
        )

    if event == "reminder.delete":
        return (
            "[Reminder] delete "
            f"source={payload.get('source')} "
            f"source_id={payload.get('source_id')} "
            f"count={payload.get('count')}"
        )

    if event == "reminder.scheduler.tick":
        return None

    if event == "reminder.trigger":
        return f"\n[Reminder] trigger id={payload.get('id')} title={payload.get('title')}"

    if event == "reminder.notification":
        return f"\n[Reminder] notification id={payload.get('id')} message={payload.get('message')}"

    if event == "reminder.completed":
        return f"\n[Reminder] completed id={payload.get('id')}"

    if event == "voice.stt.completed":
        return (
            "[Voice] STT "
            f"success={yes_no(payload.get('stt_success'))} "
            f"text={payload.get('recognized_text')}"
        )

    if event == "voice.semantic.transcript":
        corrections = payload.get("corrections") or []
        entities = payload.get("resolved_entities") or []
        pending_field = payload.get("pending_field") or "-"
        semantic_text = truncate(str(payload.get("semantic_text") or ""), 80)
        normalized_text = str(payload.get("normalized_text") or "")
        text_changed = semantic_text != truncate(normalized_text, 80)
        changed_text = " changed=YES" if text_changed else ""
        clarification_text = ""

        if payload.get("requires_clarification"):
            clarification_text = f" clarification={truncate(str(payload.get('clarification_question') or '-'), 60)}"

        return (
            "[Semantic] transcript "
            f"text=\"{semantic_text}\" "
            f"confidence={payload.get('confidence', 0)} "
            f"corrections={len(corrections)} "
            f"entities={format_semantic_entity_summary(entities)} "
            f"pending={pending_field}"
            f"{changed_text}"
            f"{clarification_text}"
        )

    if event == "voice.semantic.metrics":
        return (
            "[Semantic] metrics "
            f"entities={payload.get('entity_resolved', 0)} "
            f"resolvers={payload.get('resolver_success', 0)} "
            f"corrections={payload.get('correction_count', 0)} "
            f"semantic_conf={payload.get('semantic_confidence', 0)} "
            f"entity_avg={payload.get('entity_avg_confidence', '-')} "
            f"entity_min={payload.get('entity_min_confidence', '-')} "
            f"cache={payload.get('cache_status') or '-'} "
            f"latency={payload.get('resolver_latency_ms', 0)}ms"
        )

    if event == "voice.stt.normalized":
        corrections = payload.get("corrections") or []
        return (
            "[STT] "
            f"raw_text={payload.get('raw_text')} "
            f"normalized_text={payload.get('normalized_text')} "
            f"corrections=[{', '.join(corrections)}]"
        )

    if event == "voice.stt.recording.completed":
        return (
            "[Voice] STT recording "
            f"end_reason={payload.get('end_reason')} "
            f"recorded_seconds={payload.get('recorded_seconds')} "
            f"speech_started={yes_no(payload.get('speech_started'))} "
            f"max_rms={payload.get('max_rms', '-')} "
            f"max_dbfs={payload.get('max_dbfs', '-')}"
        )

    if event == "voice.stt.speech_started":
        return (
            "[Voice] speech_started=true "
            f"level={payload.get('level')} "
            f"rms={payload.get('rms')} "
            f"dbfs={payload.get('dbfs')} "
            f"noise_floor={payload.get('noise_floor_dbfs')} "
            f"elapsed={payload.get('elapsed')}s"
        )

    if event == "voice.stt.skipped":
        return (
            "[Voice] STT skipped "
            f"reason=invalid_input "
            f"text={payload.get('recognized_text')}"
        )

    if event == "voice.stt.provider_result":
        status = "success" if payload.get("success") else "failed"
        detail = f"text={payload.get('text')}" if payload.get("success") else f"error={payload.get('error') or '-'}"
        return (
            "[STT] provider "
            f"name={payload.get('provider')} "
            f"status={status} "
            f"{detail}"
        )

    if event == "voice.stt.openai.started":
        return (
            "[STT] openai started "
            f"provider={payload.get('provider')} "
            f"model={payload.get('model')} "
            f"language={payload.get('language') or '-'} "
            f"reason={payload.get('reason') or '-'}"
        )

    if event == "voice.stt.openai.compatibility_retry":
        return (
            "[STT] openai compatibility_retry "
            f"provider={payload.get('provider')} "
            f"model={payload.get('model')} "
            f"removed={payload.get('removed') or '-'}"
        )

    if event == "voice.stt.openai.finished":
        return (
            "[STT] openai finished "
            f"provider={payload.get('provider')} "
            f"success={yes_no(payload.get('success'))} "
            f"latency={payload.get('latency_ms', 0)}ms "
            f"text={payload.get('text')}"
        )

    if event == "voice.stt.openai.failed":
        return (
            "[STT] openai failed "
            f"provider={payload.get('provider')} "
            f"reason={payload.get('reason') or '-'} "
            f"latency={payload.get('latency_ms', 0)}ms "
            f"error={truncate(str(payload.get('error') or '-'), 160)}"
        )

    if event == "voice.stt.openai.skipped":
        return (
            "[STT] openai skipped "
            f"provider={payload.get('provider')} "
            f"reason={payload.get('reason') or '-'}"
        )

    if event == "voice.stt.fallback":
        return (
            "[STT] fallback "
            f"primary={payload.get('primary_provider')} "
            f"fallback={payload.get('fallback_provider')} "
            f"reason={payload.get('reason') or '-'} "
            f"used={yes_no(payload.get('used'))} "
            f"primary_text={payload.get('primary_text') or '-'} "
            f"fallback_text={payload.get('fallback_text') or '-'}"
        )

    if event == "voice.stt.stats":
        return (
            "[STT] stats "
            f"total={payload.get('total', 0)} "
            f"provider={payload.get('provider') or '-'} "
            f"provider_requests={payload.get('provider_requests', 0)} "
            f"success={payload.get('success_rate', 0)}% "
            f"failure={payload.get('failure_rate', 0)}% "
            f"fallback={payload.get('fallback_rate', 0)}% "
            f"correction={payload.get('correction_rate', 0)}% "
            f"confirmation_failures={payload.get('confirmation_failures', 0)} "
            f"avg_latency={payload.get('avg_latency_ms', 0)}ms"
        )

    if event == "voice.stt.audio_saved":
        return (
            "[STT] audio saved "
            f"path={payload.get('path')} "
            f"size={payload.get('size', 0)}B"
        )

    if event == "voice.pending_action.saved":
        return (
            "[Voice] pending_action saved "
            f"ability={payload.get('ability')} "
            f"action={payload.get('action')} "
            f"expires_turns={payload.get('expires_turns')}"
        )

    if event == "voice.pending_action.retry":
        return f"[Voice] pending_action retry reason={payload.get('reason')}"

    if event == "voice.confirmation.decision":
        return (
            "[Confirm] "
            f"pending_action={payload.get('pending_action')} "
            f"text=\"{payload.get('text')}\" "
            f"decision={payload.get('decision')}"
        )

    if event == "voice.confirmation.execute":
        return f"[Confirm] execute action={payload.get('pending_action')}"

    if event == "voice.intent.handled":
        return (
            "[Voice] route "
            f"ability={payload.get('routed_ability')} "
            f"success={yes_no(payload.get('ability_result_success'))}"
        )

    if event == "voice.tts.final_text":
        text = str(payload.get("final_tts_text", ""))
        return f"[TTS] text {truncate(text, 96)}"

    if event == "voice.tts.request.started":
        return (
            "[TTS] request starting "
            f"model={payload.get('model')} "
            f"voice={payload.get('voice')} "
            f"format={payload.get('response_format')}"
        )

    if event in ["voice.tts.request.finished", "voice.tts.api.completed"]:
        return (
            "[TTS] request finished "
            f"success={yes_no(payload.get('tts_api_success'))} "
            f"file={payload.get('audio_file_path')} "
            f"size={payload.get('audio_file_size')}B"
        )

    if event == "voice.tts.audio.normalized":
        return (
            "[TTS] audio normalized "
            f"changed={yes_no(payload.get('normalized'))} "
            f"reason={payload.get('reason') or '-'}"
        )

    if event == "voice.tts.audio.format":
        error = payload.get("format_error") or "-"
        return (
            "[TTS] audio format "
            f"sample_rate={payload.get('sample_rate')}Hz "
            f"channels={payload.get('channels')} "
            f"sample_width={payload.get('sample_width')}B "
            f"duration={payload.get('duration_sec')}s "
            f"error={error}"
        )

    if event == "voice.tts.audio.warning":
        return (
            "[TTS] audio warning "
            f"file={payload.get('audio_file_path')} "
            f"duration={payload.get('duration_sec')}s "
            f"text_length={payload.get('text_length')} "
            f"reason={payload.get('reason')}"
        )

    if event == "voice.tts.playback.started":
        return (
            "[TTS] playback starting "
            f"backend={payload.get('playback_backend', '-')} "
            f"file={payload.get('audio_file_path')} "
            f"size={payload.get('audio_file_size')}B"
        )

    if event == "voice.tts.playback.attempt":
        status = "success" if payload.get("playback_success") else "failed"
        return (
            "[TTS] playback attempt "
            f"backend={payload.get('playback_backend')} "
            f"status={status} "
            f"error={payload.get('playback_error') or '-'}"
        )

    if event in ["voice.tts.playback.finished", "voice.tts.playback.completed"]:
        return (
            "[TTS] playback finished "
            f"success={yes_no(payload.get('playback_success'))} "
            f"backend={payload.get('playback_backend')} "
            f"blocking={yes_no(payload.get('playback_blocking'))} "
            f"manual_heard=UNKNOWN "
            f"error={payload.get('playback_error') or '-'}"
        )

    if event == "voice.tts.playback.failed":
        return (
            "[TTS] playback finished "
            f"success=NO "
            f"backend={payload.get('playback_backend')} "
            f"blocking={yes_no(payload.get('playback_blocking'))} "
            f"error={payload.get('playback_error') or '-'}"
        )

    if event == "voice.startup":
        return f"[Runtime] startup cwd={payload.get('cwd')}"

    return f"[Trace] {event} {json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)}"


def is_raw_trace_enabled():
    """Return whether raw JSON trace lines should be printed too."""
    value = os.environ.get("JARVIS_TRACE_RAW", "")

    if value == "":
        value = read_env_file_value("JARVIS_TRACE_RAW")

    return value.lower() in ["1", "true", "yes", "on"]


def is_memory_verbose_trace_enabled():
    """Return whether detailed Memory internals should be printed."""
    value = os.environ.get("JARVIS_MEMORY_TRACE_VERBOSE", "")

    if value == "":
        value = read_env_file_value("JARVIS_MEMORY_TRACE_VERBOSE")

    return value.lower() in ["1", "true", "yes", "on"]


def yes_no(value):
    """Format booleans as YES/NO."""
    return "YES" if bool(value) else "NO"


def truncate(text, max_length):
    """Return shortened text for one-line trace output."""
    if len(text) <= max_length:
        return text

    return f"{text[: max_length - 3]}..."


def format_semantic_entity_summary(entities):
    """Return a compact semantic entity summary."""
    if not entities:
        return "-"

    values = []

    for entity in entities[:3]:
        entity_type = entity.get("type") or "entity"
        value = entity.get("value") or entity.get("id") or "-"
        confidence = entity.get("confidence")
        confidence_text = f":{confidence}" if confidence is not None else ""
        values.append(f"{entity_type}:{value}{confidence_text}")

    if len(entities) > 3:
        values.append(f"+{len(entities) - 3}")

    return "[" + ",".join(values) + "]"


def read_debug_trace_value():
    """Read JARVIS_DEBUG_TRACE from process env or local .env."""
    value = os.environ.get("JARVIS_DEBUG_TRACE", "")

    if value != "":
        return value

    return read_env_file_value("JARVIS_DEBUG_TRACE")


def read_env_file_value(key):
    """Read one value from a local .env file."""
    env_path = Path(".env")

    if not env_path.exists():
        return ""

    with env_path.open("r", encoding="utf-8") as file:
        for line in file:
            env_key, value = parse_env_line(line)

            if env_key == key:
                return value

    return ""


def parse_env_line(line):
    """Parse a simple KEY=VALUE line."""
    stripped_line = line.strip()

    if stripped_line == "" or stripped_line.startswith("#") or "=" not in stripped_line:
        return "", ""

    key, value = stripped_line.split("=", 1)
    return key.strip(), clean_env_value(value)


def clean_env_value(value):
    """Remove simple wrapping quotes."""
    cleaned = value.strip()

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        if cleaned[0] in ["'", '"']:
            return cleaned[1:-1]

    return cleaned
