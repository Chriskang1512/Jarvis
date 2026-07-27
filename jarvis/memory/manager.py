"""Single entry point for working, durable, and preference memory."""

from jarvis.debug_trace import trace_event
from jarvis.memory.models import MemoryContext, MemoryRecord, MemoryType
from jarvis.memory.policy import MemoryStorePolicy


class MemoryManager:
    def __init__(self, provider, store_policy=None, session_id="default"):
        self.provider = provider
        self.store_policy = store_policy or MemoryStorePolicy()
        self.session_id = str(session_id or "default")

    def store(
        self,
        key,
        value,
        memory_type=MemoryType.LONG_TERM,
        scope="user",
        source="user",
        confidence=1.0,
        metadata=None,
    ):
        normalized_type = (
            memory_type
            if isinstance(memory_type, MemoryType)
            else MemoryType(str(memory_type))
        )
        record = MemoryRecord(
            key=str(key).strip(),
            value=str(value).strip(),
            memory_type=normalized_type,
            scope=str(scope),
            session_id=self.session_id
            if normalized_type == MemoryType.WORKING
            else "",
            source=str(source),
            confidence=float(confidence),
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
        return saved

    def remember_working(self, key, value, metadata=None):
        return self.store(
            key,
            value,
            MemoryType.WORKING,
            scope="session",
            metadata=metadata,
        )

    def retrieve(self, query="", limit=20):
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
        return MemoryContext(tuple(records))

    def apply_store_policy(self, text, source="user"):
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
            confidence=decision.confidence,
            metadata={"policy_reason": decision.reason},
        )

    def observe_execution(self, tool_request, result):
        if not getattr(result, "success", False):
            return None
        input_data = dict(getattr(tool_request, "input_data", {}) or {})
        text = input_data.get("text") or input_data.get("raw_text") or ""
        return self.apply_store_policy(text, source="post_execution")

    def clear_working(self):
        return self.provider.clear_working(self.session_id)


class EntityGraphStub:
    status = "stub"


class PersonalLexiconStub:
    status = "stub"


class CorrectionMemoryStub:
    status = "stub"


class CloudMemoryProviderStub:
    provider_name = "cloud_stub"
    status = "stub"
