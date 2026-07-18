"""In-memory Core EventBus."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
import time
from time import perf_counter
import uuid

from jarvis.core.events.context import EventContext
from jarvis.core.events.exceptions import EventHandlerTimeout, TemporaryEventHandlerError
from jarvis.core.events.metrics import EventBusMetrics
from jarvis.debug_trace import trace_event


WILDCARD_EVENT = "*"
BACKOFF_NONE = "none"
BACKOFF_FIXED = "fixed"
BACKOFF_EXPONENTIAL = "exponential"


@dataclass(frozen=True)
class RetryPolicy:
    """Synchronous retry policy for one handler subscription."""

    max_attempts: int = 1
    retry_delay_ms: int = 0
    backoff_strategy: str = BACKOFF_NONE
    retryable_errors: tuple = field(default_factory=lambda: (TemporaryEventHandlerError, TimeoutError, EventHandlerTimeout))

    def should_retry(self, error, attempt):
        """Return whether another attempt should be made."""
        if attempt >= max(1, int(self.max_attempts)):
            return False

        if self.backoff_strategy == BACKOFF_NONE:
            return False

        return isinstance(error, self.retryable_errors)

    def delay_for_attempt(self, attempt):
        """Return delay in seconds before the next attempt."""
        delay_ms = max(0, int(self.retry_delay_ms))

        if self.backoff_strategy == BACKOFF_EXPONENTIAL:
            delay_ms = delay_ms * (2 ** max(0, attempt - 1))

        return delay_ms / 1000


@dataclass(frozen=True)
class HandlerSubscription:
    """One EventBus handler subscription."""

    token: str
    event_type: str
    handler: object
    priority: int = 100
    order: int = 0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    handler_timeout_ms: int = 0


@dataclass(frozen=True)
class HandlerResult:
    """One handler execution result."""

    handler: str
    success: bool
    attempts: int = 1
    latency_ms: int = 0
    error_type: str = ""
    error_message: str = ""
    dead_letter_id: str = ""

    @property
    def error(self):
        """Backward-compatible error alias."""
        return self.error_message


@dataclass(frozen=True)
class PublishResult:
    """Result of publishing one event."""

    event: object
    handler_results: tuple[HandlerResult, ...] = field(default_factory=tuple)
    duplicate: bool = False
    execution_time_ms: int = 0
    dead_letters_created: int = 0

    @property
    def success(self):
        """Return whether publish completed without handler failures."""
        return not self.duplicate and all(result.success for result in self.handler_results)

    @property
    def event_id(self):
        """Return published event ID."""
        return getattr(self.event, "event_id", "")

    @property
    def event_type(self):
        """Return published event type."""
        return getattr(self.event, "event_type", "")

    @property
    def trace_id(self):
        """Return trace ID."""
        return getattr(self.event, "trace_id", "")

    @property
    def correlation_id(self):
        """Return correlation ID."""
        return getattr(self.event, "correlation_id", "")

    @property
    def handlers_total(self):
        """Return total attempted handlers."""
        return len(self.handler_results)

    @property
    def handlers_succeeded(self):
        """Return successful handler count."""
        return sum(1 for result in self.handler_results if result.success)

    @property
    def handlers_failed(self):
        """Return failed handler count."""
        return sum(1 for result in self.handler_results if not result.success)

    @property
    def handlers_retried(self):
        """Return handlers that required more than one attempt."""
        return sum(1 for result in self.handler_results if result.attempts > 1)

    def to_dict(self):
        """Return a structured publish result."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "success": self.success,
            "duplicate": self.duplicate,
            "handlers_total": self.handlers_total,
            "handlers_succeeded": self.handlers_succeeded,
            "handlers_failed": self.handlers_failed,
            "handlers_retried": self.handlers_retried,
            "dead_letters_created": self.dead_letters_created,
            "execution_time_ms": self.execution_time_ms,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "handler_results": [result.__dict__ for result in self.handler_results],
        }


@dataclass(frozen=True)
class IdempotencyRecord:
    """One processed business event key."""

    idempotency_key: str
    event_id: str
    processed_at: str
    result_digest: str = ""


class InMemoryIdempotencyStore:
    """Small in-memory idempotency store with TTL/max-size pruning."""

    def __init__(self, ttl_seconds=3600, max_size=1000):
        """Create store."""
        self.ttl_seconds = int(ttl_seconds)
        self.max_size = int(max_size)
        self.records = {}

    def get(self, key):
        """Return a valid record by key."""
        self.prune()
        return self.records.get(str(key or ""))

    def put(self, key, event_id, result_digest=""):
        """Store one processed key."""
        key = str(key or "")

        if key == "":
            return None

        self.records[key] = IdempotencyRecord(
            idempotency_key=key,
            event_id=str(event_id or ""),
            processed_at=datetime.now().isoformat(timespec="seconds"),
            result_digest=str(result_digest or ""),
        )
        self.prune()
        return self.records[key]

    def prune(self):
        """Prune old or excess records."""
        now = datetime.now()
        ttl = timedelta(seconds=max(0, self.ttl_seconds))

        if self.ttl_seconds > 0:
            self.records = {
                key: record
                for key, record in self.records.items()
                if now - datetime.fromisoformat(record.processed_at) <= ttl
            }

        if self.max_size > 0 and len(self.records) > self.max_size:
            ordered = sorted(self.records.values(), key=lambda item: item.processed_at)
            keep = {record.idempotency_key for record in ordered[-self.max_size :]}
            self.records = {key: value for key, value in self.records.items() if key in keep}


class InMemoryEventBus:
    """Synchronous in-process EventBus with handler isolation."""

    def __init__(self, recorder=None, dead_letter_recorder=None, idempotency_store=None):
        """Create an empty event bus."""
        self.subscribers = {}
        self.metrics = EventBusMetrics()
        self.recorder = recorder
        self.dead_letter_recorder = dead_letter_recorder
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()
        self._delivered = set()
        self._subscription_order = 0

    def subscribe(self, event_type, handler, priority=100, retry_policy=None, handler_timeout_ms=0):
        """Subscribe one handler to an event type or wildcard."""
        event_type = str(event_type or WILDCARD_EVENT)
        token = f"sub-{uuid.uuid4().hex[:10]}"
        self._subscription_order += 1
        self.subscribers.setdefault(event_type, {})[token] = HandlerSubscription(
            token=token,
            event_type=event_type,
            handler=handler,
            priority=int(priority),
            order=self._subscription_order,
            retry_policy=retry_policy or RetryPolicy(),
            handler_timeout_ms=int(handler_timeout_ms or 0),
        )
        return token

    def unsubscribe(self, token):
        """Remove a subscription by token."""
        for handlers in self.subscribers.values():
            if token in handlers:
                del handlers[token]
                return True
        return False

    def publish(self, event, context=None, bypass_idempotency=False, handler_names=None):
        """Publish one event to matching handlers."""
        started = perf_counter()
        event = apply_event_context(event, context)
        self.metrics.event_published += 1
        self.metrics.queue_size = 1
        trace_event(
            "event.publish",
            event_type=getattr(event, "event_type", ""),
            event_id=getattr(event, "event_id", ""),
            aggregate_id=getattr(event, "aggregate_id", ""),
            trace_id=getattr(event, "trace_id", ""),
            correlation_id=getattr(event, "correlation_id", ""),
            causation_id=getattr(event, "causation_id", ""),
        )

        idempotency_key = str(getattr(event, "idempotency_key", "") or "")

        if idempotency_key and not bypass_idempotency and self.idempotency_store.get(idempotency_key) is not None:
            self.metrics.duplicate_skipped += 1
            self.metrics.queue_size = 0
            duration = elapsed_ms(started)
            self.metrics.record_publish_latency(duration)
            trace_event(
                "event.completed",
                event_type=getattr(event, "event_type", ""),
                event_id=getattr(event, "event_id", ""),
                handled=0,
                failed=0,
                duplicate=True,
            )
            return PublishResult(event=event, handler_results=tuple(), duplicate=True, execution_time_ms=duration)

        if self.recorder is not None:
            self.recorder.record(event)

        results = []

        for subscription in self.matching_handlers(event, handler_names=handler_names):
            token = subscription.token
            handler = subscription.handler
            delivery_key = (getattr(event, "event_id", ""), token)

            if delivery_key in self._delivered:
                self.metrics.duplicate_skipped += 1
                continue

            self._delivered.add(delivery_key)
            results.append(self.call_handler(subscription, event))

        self.metrics.queue_size = 0
        duration = elapsed_ms(started)
        self.metrics.record_publish_latency(duration)
        dead_letters_created = sum(1 for result in results if result.dead_letter_id)

        if idempotency_key:
            self.idempotency_store.put(idempotency_key, getattr(event, "event_id", ""), digest_handler_results(results))

        trace_event(
            "event.completed",
            event_type=getattr(event, "event_type", ""),
            event_id=getattr(event, "event_id", ""),
            handled=sum(1 for result in results if result.success),
            failed=sum(1 for result in results if not result.success),
            duplicate=False,
            latency_ms=duration,
        )
        return PublishResult(
            event=event,
            handler_results=tuple(results),
            duplicate=False,
            execution_time_ms=duration,
            dead_letters_created=dead_letters_created,
        )

    def matching_handlers(self, event, handler_names=None):
        """Return matching subscriptions in priority order."""
        event_type = getattr(event, "event_type", "")
        allowed = set(handler_names or [])
        matched = []
        matched.extend(self.subscribers.get(event_type, {}).values())
        matched.extend(self.subscribers.get(WILDCARD_EVENT, {}).values())
        matched = sorted(matched, key=lambda item: (-item.priority, item.order))

        if not allowed:
            return matched

        return [item for item in matched if handler_display_name(item.handler) in allowed]

    def call_handler(self, subscription, event):
        """Call one handler without letting failures stop the bus."""
        handler = subscription.handler
        handler_name = handler_display_name(handler)
        started = perf_counter()
        attempts = 0
        last_error = None

        while attempts < max(1, subscription.retry_policy.max_attempts):
            attempts += 1
            attempt_started = perf_counter()

            try:
                handle_event(handler, event)
                attempt_latency = elapsed_ms(attempt_started)

                if subscription.handler_timeout_ms and attempt_latency > subscription.handler_timeout_ms:
                    raise EventHandlerTimeout(
                        f"handler timeout after {attempt_latency}ms > {subscription.handler_timeout_ms}ms"
                    )

                latency_ms = elapsed_ms(started)
                self.metrics.event_handled += 1
                self.metrics.record_handler_latency(handler_name, latency_ms)
                trace_event(
                    "event.handler",
                    event_type=getattr(event, "event_type", ""),
                    event_id=getattr(event, "event_id", ""),
                    handler=handler_name,
                    success=True,
                    latency_ms=latency_ms,
                    attempt=attempts,
                )
                return HandlerResult(handler=handler_name, success=True, attempts=attempts, latency_ms=latency_ms)
            except Exception as error:
                last_error = error

                if subscription.retry_policy.should_retry(error, attempts):
                    self.metrics.event_retried += 1
                    trace_event(
                        "event.handler_retry",
                        event_type=getattr(event, "event_type", ""),
                        event_id=getattr(event, "event_id", ""),
                        handler=handler_name,
                        attempt=attempts + 1,
                        max_attempts=subscription.retry_policy.max_attempts,
                        error=str(error),
                    )
                    delay = subscription.retry_policy.delay_for_attempt(attempts)
                    if delay > 0:
                        time.sleep(delay)
                    continue
                break

        latency_ms = elapsed_ms(started)
        self.metrics.event_failed += 1
        self.metrics.record_handler_latency(handler_name, latency_ms)
        dead_letter_id = ""

        if self.dead_letter_recorder is not None:
            dead_letter_id = self.dead_letter_recorder.record_failure(event, handler_name, last_error) or ""
            if dead_letter_id:
                self.metrics.dead_letter_total += 1

        trace_event(
            "event.handler",
            event_type=getattr(event, "event_type", ""),
            event_id=getattr(event, "event_id", ""),
            handler=handler_name,
            success=False,
            latency_ms=latency_ms,
            attempt=attempts,
            error=str(last_error),
        )
        return HandlerResult(
            handler=handler_name,
            success=False,
            attempts=attempts,
            latency_ms=latency_ms,
            error_type=last_error.__class__.__name__ if last_error is not None else "",
            error_message=str(last_error or ""),
            dead_letter_id=dead_letter_id,
        )

    def flush(self):
        """Flush EventBus recorders."""
        if self.recorder is not None and hasattr(self.recorder, "flush"):
            self.recorder.flush()
        if self.dead_letter_recorder is not None and hasattr(self.dead_letter_recorder, "flush"):
            self.dead_letter_recorder.flush()
        return True

    def close(self):
        """Flush and close EventBus resources."""
        self.flush()
        if self.recorder is not None and hasattr(self.recorder, "close"):
            self.recorder.close()
        if self.dead_letter_recorder is not None and hasattr(self.dead_letter_recorder, "close"):
            self.dead_letter_recorder.close()
        return True


def handle_event(handler, event):
    """Invoke either object-style or callable handlers."""
    if hasattr(handler, "handle"):
        return handler.handle(event)
    return handler(event)


def handler_display_name(handler):
    """Return a stable handler name for logs and metrics."""
    if hasattr(handler, "name"):
        return str(handler.name)
    if hasattr(handler, "__name__"):
        return str(handler.__name__)
    return handler.__class__.__name__


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)


def apply_event_context(event, context):
    """Return event with context fields filled when provided."""
    if context is None:
        return event

    if isinstance(context, dict):
        context = EventContext(**context)

    metadata = dict(getattr(event, "metadata", {}) or {})
    metadata.update(context.to_metadata())

    return replace(
        event,
        idempotency_key=getattr(event, "idempotency_key", "") or getattr(context, "idempotency_key", ""),
        trace_id=getattr(event, "trace_id", "") or context.trace_id,
        correlation_id=getattr(event, "correlation_id", "") or context.correlation_id,
        causation_id=getattr(event, "causation_id", "") or getattr(context, "causation_id", ""),
        source=getattr(event, "source", "") or context.source,
        metadata=metadata,
    )


def digest_handler_results(results):
    """Return a small digest for idempotency records."""
    text = "|".join(
        f"{result.handler}:{result.success}:{result.attempts}:{result.error_type}:{result.error_message}"
        for result in results
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
