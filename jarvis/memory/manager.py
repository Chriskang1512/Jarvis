"""Single entry point for working, durable, and preference memory."""

from datetime import datetime, timedelta, timezone
import hashlib

from jarvis.core.events import BaseEvent
from jarvis.debug_trace import trace_event
from jarvis.memory.models import MemoryContext, MemoryRecord, MemoryType
from jarvis.memory.policy import MemoryStorePolicy


class MemoryManager:
    def __init__(
        self,
        provider,
        store_policy=None,
        session_id="default",
        event_bus=None,
        default_source="user",
        default_source_provider="",
        default_created_by="user",
        working_ttl_seconds=1800,
    ):
        self.provider = provider
        self.store_policy = store_policy or MemoryStorePolicy()
        self.session_id = str(session_id or "default")
        self.event_bus = event_bus
        self.default_source = str(default_source or "user")
        self.default_source_provider = str(default_source_provider or "")
        self.default_created_by = str(default_created_by or "user")
        self.working_ttl_seconds = max(1, int(working_ttl_seconds))

    def store(
        self,
        key,
        value,
        memory_type=MemoryType.LONG_TERM,
        scope="user",
        source=None,
        source_provider=None,
        created_by=None,
        confidence=1.0,
        ttl_seconds=None,
        expires_at="",
        metadata=None,
    ):
        normalized_type = (
            memory_type
            if isinstance(memory_type, MemoryType)
            else MemoryType(str(memory_type))
        )
        existing = self.provider.get(
            str(key).strip(),
            memory_type=normalized_type,
            session_id=self.session_id if normalized_type == MemoryType.WORKING else "",
        )
        expiry = str(expires_at or "")
        if normalized_type == MemoryType.WORKING and expiry == "":
            ttl = self.working_ttl_seconds if ttl_seconds is None else max(1, int(ttl_seconds))
            expiry = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        record = MemoryRecord(
            key=str(key).strip(),
            value=str(value).strip(),
            memory_type=normalized_type,
            scope=str(scope),
            session_id=self.session_id
            if normalized_type == MemoryType.WORKING
            else "",
            source=str(source or self.default_source),
            source_provider=str(
                self.default_source_provider
                if source_provider is None
                else source_provider
            ),
            created_by=str(created_by or self.default_created_by),
            confidence=normalize_confidence(confidence),
            expires_at=expiry,
            metadata=dict(metadata or {}),
        )
        saved = self.provider.upsert(record)
        trace_event(
            "memory.manager.store",
            key=saved.key,
            memory_type=saved.memory_type.value,
            provider=self.provider.provider_name,
            value_length=len(saved.value),
        )
        self.publish_memory_event(
            "MemoryUpdated" if existing is not None else "MemoryStored",
            saved,
        )
        return saved

    def remember_working(self, key, value, metadata=None, ttl_seconds=None):
        return self.store(
            key,
            value,
            MemoryType.WORKING,
            scope="session",
            ttl_seconds=ttl_seconds,
            metadata=metadata,
        )

    def retrieve(self, query="", limit=20):
        expired = self.provider.purge_expired(datetime.now(timezone.utc).isoformat())
        if expired:
            trace_event("memory.manager.expired", count=len(expired))
            for record in expired:
                self.publish_memory_event("MemoryDeleted", record, reason="ttl_expired")
        records = self.provider.search(
            query=query,
            memory_types=(
                MemoryType.WORKING,
                MemoryType.LONG_TERM,
                MemoryType.PREFERENCE,
            ),
            session_id=self.session_id,
            limit=limit,
        )
        if query and not records:
            records = self.provider.search(
                memory_types=(MemoryType.PREFERENCE,),
                session_id=self.session_id,
                limit=limit,
            )
        trace_event(
            "memory.manager.retrieve",
            provider=self.provider.provider_name,
            query_length=len(str(query or "")),
            result_count=len(records),
        )
        self.publish_retrieved_event(records, query)
        return MemoryContext(tuple(records))

    def apply_store_policy(
        self,
        text,
        source=None,
        source_provider=None,
        created_by=None,
    ):
        decision = self.store_policy.decide(text)
        trace_event(
            "memory.store_policy",
            should_store=decision.should_store,
            reason=decision.reason,
            memory_type=decision.memory_type.value if decision.memory_type else "",
        )
        if not decision.should_store:
            return None
        return self.store(
            decision.key,
            decision.value,
            decision.memory_type,
            source=source,
            source_provider=source_provider,
            created_by=created_by,
            confidence=decision.confidence,
            metadata={"policy_reason": decision.reason},
        )

    def observe_execution(self, tool_request, result):
        if not getattr(result, "success", False):
            return None
        input_data = dict(getattr(tool_request, "input_data", {}) or {})
        text = input_data.get("text") or input_data.get("raw_text") or ""
        return self.apply_store_policy(text)

    def delete(self, key, memory_type=None):
        normalized_type = (
            memory_type
            if isinstance(memory_type, MemoryType) or memory_type is None
            else MemoryType(str(memory_type))
        )
        existing = self.provider.get(
            key,
            memory_type=normalized_type,
            session_id=self.session_id if normalized_type == MemoryType.WORKING else "",
        )
        deleted = self.provider.delete(
            key,
            memory_type=normalized_type,
            session_id=self.session_id if normalized_type == MemoryType.WORKING else "",
        )
        if existing is not None and deleted:
            self.publish_memory_event("MemoryDeleted", existing)
        return deleted

    def clear_working(self):
        records = self.provider.search(
            memory_types=(MemoryType.WORKING,),
            session_id=self.session_id,
            limit=1000,
        )
        deleted = self.provider.clear_working(self.session_id)
        for record in records:
            if record.memory_type == MemoryType.WORKING:
                self.publish_memory_event("MemoryDeleted", record)
        return deleted

    def publish_memory_event(self, event_type, record, reason=""):
        if self.event_bus is None:
            return None
        return self.event_bus.publish(
            BaseEvent(
                event_type=event_type,
                aggregate_type="Memory",
                aggregate_id=record.id,
                idempotency_key=f"{event_type}:{record.id}:{record.updated_at}",
                source="memory_manager",
                payload={
                    **memory_event_payload(record),
                    **({"reason": reason} if reason else {}),
                },
                metadata={"repository_provider": self.provider.provider_name},
            )
        )

    def publish_retrieved_event(self, records, query):
        if self.event_bus is None:
            return None
        query_fingerprint = fingerprint(query)
        return self.event_bus.publish(
            BaseEvent(
                event_type="MemoryRetrieved",
                aggregate_type="MemoryQuery",
                aggregate_id=f"{self.session_id}:{query_fingerprint[:12]}",
                idempotency_key=(
                    f"MemoryRetrieved:{self.session_id}:{query_fingerprint}:"
                    f"{datetime.now(timezone.utc).isoformat()}"
                ),
                source="memory_manager",
                payload={
                    "session_fingerprint": fingerprint(self.session_id),
                    "query_fingerprint": query_fingerprint,
                    "result_count": len(records),
                    "memory_ids": [record.id for record in records],
                },
                metadata={"repository_provider": self.provider.provider_name},
            )
        )


def normalize_confidence(value):
    return max(0.0, min(1.0, float(value)))


def fingerprint(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def memory_event_payload(record):
    return {
        "memory_id": record.id,
        "memory_type": record.memory_type.value,
        "scope": record.scope,
        "key_fingerprint": fingerprint(record.key),
        "source": record.source,
        "source_provider": record.source_provider,
        "created_by": record.created_by,
        "confidence": record.confidence,
        "expires_at": record.expires_at,
    }


class EntityGraphStub:
    status = "stub"


class PersonalLexiconStub:
    status = "stub"


class CorrectionMemoryStub:
    status = "stub"


class CloudMemoryProviderStub:
    provider_name = "cloud_stub"
    status = "stub"
