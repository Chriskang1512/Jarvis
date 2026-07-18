import json
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.memory.models import MemoryResult, create_memory_entry
from jarvis.abilities.native.memory.parser import MemoryIntentParser
from jarvis.abilities.native.memory.storage import JsonMemoryStorage
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.debug_trace import trace_event
from jarvis.permissions import PermissionLevel


class MemoryAbility:
    """Native persistent ability for storing and recalling user memory."""

    def __init__(self, storage=None, metadata=None, parser=None):
        """Create Memory Ability with replaceable storage."""
        self.storage = storage or JsonMemoryStorage()
        self.metadata = metadata or load_memory_metadata()
        self.parser = parser or MemoryIntentParser()

    @property
    def id(self):
        """Return the stable ability ID."""
        return self.metadata.id

    @property
    def name(self):
        """Return the display ability name."""
        return self.metadata.name

    @property
    def type(self):
        """Return the ability execution type."""
        return self.metadata.type

    @property
    def description(self):
        """Return the ability description."""
        return self.metadata.description

    @property
    def permission(self):
        """Return the required permission level."""
        return self.metadata.permission

    def execute(self, input_data):
        """Execute a memory action and return an AbilityResult."""
        started = perf_counter()

        try:
            query = normalize_query(input_data, self.parser)
            trace_event(
                "memory.query",
                action=query.action,
                key=query.key,
                scope=query.scope,
                category=query.category,
                confidence=query.confidence,
            )
            result = self.execute_query(query)
            trace_event(
                "memory.result",
                action=result.action,
                key=result.key,
                found=result.found,
                entries=len(result.entries),
                success=True,
            )
            trace_memory_summary(query, result, elapsed_ms(started))
            return AbilityResult(
                success=True,
                data=result,
                metadata={
                    "ability_id": self.id,
                    "storage": getattr(self.storage, "provider_name", ""),
                    "query": query,
                },
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    def execute_query(self, query):
        """Dispatch one normalized MemoryQuery."""
        if query.action == "remember":
            return self.remember(query)

        if query.action == "recall":
            return self.recall(query)

        if query.action == "forget":
            return self.forget(query)

        if query.action == "list":
            return self.list(query)

        raise ValueError(f"Unsupported memory action: {query.action}")

    def remember(self, query):
        """Store or update one memory entry."""
        if query.key == "" or query.value == "":
            raise ValueError("Memory remember requires both key and value.")

        existing = self.storage.get(query.key, query.scope)
        entry = create_memory_entry(query, existing=existing)
        saved = self.storage.upsert(entry)
        return MemoryResult(action="remember", entry=saved, key=saved.key, found=True)

    def recall(self, query):
        """Recall one memory entry."""
        if query.key == "":
            raise ValueError("Memory recall requires a key.")

        entry = self.storage.get(query.key, query.scope)
        source = "canonical"

        if entry is None:
            entry = self.storage.get(query.key)

        if entry is None:
            entry = self.recall_legacy_entry(query)
            source = "legacy" if entry is not None else "miss"

        return MemoryResult(action="recall", entry=entry, key=query.key, found=entry is not None, source=source)

    def recall_legacy_entry(self, query):
        """Return and migrate a known legacy entry for a canonical key."""
        legacy_keys = legacy_keys_for(query.key)

        for legacy_key in legacy_keys:
            entry = self.storage.get(legacy_key, query.scope) or self.storage.get(legacy_key)

            if entry is None:
                continue

            migrated = replace(entry, key=query.key, value=normalize_legacy_memory_value(query.key, entry.value))
            self.storage.upsert(migrated)
            trace_event("memory.legacy_key_fallback", legacy_key=legacy_key, canonical_key=query.key)
            return migrated

        return None

    def forget(self, query):
        """Forget one memory entry."""
        if query.key == "":
            raise ValueError("Memory forget requires a key.")

        if not query.confirmed:
            return MemoryResult(
                action="forget",
                key=query.key,
                found=False,
                message="이 기억을 삭제하려면 확인이 필요합니다.",
            )

        deleted = self.storage.delete(query.key, query.scope)

        if len(deleted) == 0:
            deleted = self.storage.delete(query.key)

        return MemoryResult(action="forget", entries=deleted, key=query.key, found=len(deleted) > 0, source="storage")

    def list(self, query):
        """List memory entries."""
        entries = self.storage.list(scope=None if query.scope == "" else query.scope)
        return MemoryResult(action="list", entries=entries, found=len(entries) > 0, source="storage")

    def health(self):
        """Return Memory storage health."""
        if hasattr(self.storage, "health"):
            return self.storage.health()

        return AbilityHealth(status="ok", provider=getattr(self.storage, "provider_name", ""))


def load_memory_metadata():
    """Load Memory metadata from manifest."""
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
        output_schema=manifest.get("output_schema", "MemoryResult"),
        aliases=[
            "remember",
            "forget",
            "언제",
            "언제야",
            "언제였지",
            "처음 만난",
            "처음 만난 날",
            "기억",
            "기억해",
            "기억해.",
            "잊어",
            "기억 목록",
            "내 이름",
        ],
        supported_intents=[
            "memory.remember",
            "memory.recall",
            "memory.forget",
            "memory.list",
            "아야 처음 만난 날이 언제야",
            "아야 처음 만난 게 언제였지",
            "기억해",
            "기억해.",
            "내 이름 뭐야",
            "잊어",
            "무엇을 기억하고 있어",
        ],
        examples=[
            "내 이름은 크리스야. 앞으로 기억해.",
            "내 이름이 뭐야?",
            "내 이름 잊어.",
            "무엇을 기억하고 있어?",
        ],
        input_prefixes=["remember", "forget"],
        route_confidence=0.75,
    )


def normalize_query(input_data, parser=None):
    """Return a MemoryQuery from direct query or text input."""
    if hasattr(input_data, "action") and hasattr(input_data, "key"):
        return input_data

    if isinstance(input_data, dict):
        if "action" in input_data:
            return parser_query_from_dict(input_data)

        raw_text = input_data.get("raw_text") or input_data.get("text") or input_data.get("key") or ""
    else:
        raw_text = str(input_data or "")

    parser = parser or MemoryIntentParser()
    return parser.parse(raw_text)


def parser_query_from_dict(input_data):
    """Create a MemoryQuery from explicit API input."""
    from jarvis.abilities.native.memory.models import MemoryQuery

    return MemoryQuery(
        action=str(input_data.get("action", "")),
        key=str(input_data.get("key", "")),
        value=str(input_data.get("value", "")),
        category=str(input_data.get("category", "general")),
        scope=str(input_data.get("scope", "long_term")),
        raw_text=str(input_data.get("raw_text", "")),
        source=str(input_data.get("source", "user")),
        confidence=float(input_data.get("confidence", 0.75)),
        confirmed=bool(input_data.get("_confirmed", input_data.get("confirmed", False))),
        event=dict(input_data.get("event", {})),
    )


def create_ability(storage=None):
    """Create the native Memory ability."""
    return MemoryAbility(storage=storage)


def legacy_keys_for(key):
    """Return legacy keys that should resolve to one canonical memory key."""
    if key == "relationship.aya.birthday":
        return ["general.아야_생일"]

    return []


def normalize_legacy_memory_value(key, value):
    """Normalize a legacy stored value for a canonical memory key."""
    if key == "relationship.aya.birthday":
        from jarvis.abilities.native.memory.parser import extract_date_iso

        date_value = extract_date_iso(str(value))

        if date_value != "":
            return date_value

    return value


def trace_memory_summary(query, result, duration_ms):
    """Emit one compact memory trace for runtime debugging."""
    entity, attribute = memory_key_parts(result.key or query.key)
    value = memory_result_value(result)

    trace_event(
        "memory.summary",
        intent=result.action or query.action,
        entity=entity,
        attribute=attribute,
        canonical_key=result.key or query.key,
        source=result.source,
        found=result.found,
        value=value,
        duration_ms=duration_ms,
    )


def memory_key_parts(key):
    """Return readable entity and attribute parts from a memory key."""
    parts = str(key or "").split(".")

    if len(parts) >= 3 and parts[0] == "relationship":
        return parts[1], ".".join(parts[2:])

    if len(parts) >= 2:
        return parts[0], ".".join(parts[1:])

    return "-", "-"


def memory_result_value(result):
    """Return a compact value for memory summary traces."""
    if result.entry is not None:
        return result.entry.value

    if len(result.entries) > 0:
        return str(len(result.entries))

    return ""


def elapsed_ms(started):
    """Return elapsed milliseconds from a perf_counter start."""
    return int((perf_counter() - started) * 1000)
