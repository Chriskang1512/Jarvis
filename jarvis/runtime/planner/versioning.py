from collections import deque
from dataclasses import dataclass


class ContractNegotiationError(ValueError):
    """Fail-closed contract negotiation error with a stable code."""

    def __init__(self, code, message=""):
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class ContractSupport:
    """Contract versions one component can consume or produce."""

    component: str
    supported_versions: tuple[str, ...]
    preferred_version: str = ""

    def __post_init__(self):
        versions = tuple(dict.fromkeys(normalize_contract_version(item) for item in self.supported_versions))
        if not versions:
            raise ContractNegotiationError("SUPPORTED_VERSIONS_REQUIRED")
        preferred = normalize_contract_version(self.preferred_version) if self.preferred_version else versions[0]
        if preferred not in versions:
            raise ContractNegotiationError("PREFERRED_VERSION_NOT_SUPPORTED")
        object.__setattr__(self, "supported_versions", versions)
        object.__setattr__(self, "preferred_version", preferred)


@dataclass(frozen=True)
class VersionAdapter:
    """Registered deterministic conversion between contract versions."""

    name: str
    from_version: str
    to_version: str
    convert: object

    def __post_init__(self):
        object.__setattr__(self, "from_version", normalize_contract_version(self.from_version))
        object.__setattr__(self, "to_version", normalize_contract_version(self.to_version))
        if not callable(self.convert):
            raise ContractNegotiationError("VERSION_ADAPTER_NOT_CALLABLE")


@dataclass(frozen=True)
class ContractNegotiationResult:
    producer_version: str
    selected_version: str
    adapter_names: tuple[str, ...] = ()

    @property
    def direct(self):
        return not self.adapter_names


class VersionAdapterRegistry:
    """Store deterministic contract converters and resolve shortest paths."""

    def __init__(self):
        self._adapters = {}

    def register(self, adapter):
        key = (adapter.from_version, adapter.to_version)
        if key in self._adapters:
            raise ContractNegotiationError("VERSION_ADAPTER_ALREADY_REGISTERED")
        self._adapters[key] = adapter

    def find_path(self, from_version, target_versions):
        source = normalize_contract_version(from_version)
        targets = {normalize_contract_version(item) for item in target_versions}
        queue = deque([(source, ())])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            if current in targets:
                return path
            candidates = sorted(
                (
                    adapter
                    for (adapter_source, _), adapter in self._adapters.items()
                    if adapter_source == current
                ),
                key=lambda item: (item.to_version, item.name),
                reverse=True,
            )
            for adapter in candidates:
                if adapter.to_version in visited:
                    continue
                visited.add(adapter.to_version)
                queue.append((adapter.to_version, path + (adapter,)))
        return ()

    def adapt(self, value, path):
        converted = value
        for adapter in path:
            converted = adapter.convert(converted)
        return converted


class ContractVersionNegotiator:
    """Select a common version or an explicit adapter path."""

    def __init__(self, adapter_registry=None):
        self.adapter_registry = adapter_registry or VersionAdapterRegistry()

    def negotiate(self, producer, consumer):
        common = set(producer.supported_versions) & set(consumer.supported_versions)
        if common:
            selected = max(common, key=contract_version_sort_key)
            return ContractNegotiationResult(selected, selected)

        producer_versions = _preferred_first(producer)
        for source in producer_versions:
            path = self.adapter_registry.find_path(source, consumer.supported_versions)
            if path:
                return ContractNegotiationResult(
                    producer_version=source,
                    selected_version=path[-1].to_version,
                    adapter_names=tuple(adapter.name for adapter in path),
                )
        raise ContractNegotiationError(
            "CONTRACT_VERSION_NOT_NEGOTIABLE",
            f"{producer.component} and {consumer.component} have no compatible contract version.",
        )


def normalize_contract_version(version):
    """Normalize numeric contract labels while preserving named legacy labels."""
    value = str(version or "").strip().lower()
    if not value:
        raise ContractNegotiationError("CONTRACT_VERSION_REQUIRED")
    if value.startswith("v") and value[1:2].isdigit():
        value = value[1:]
    if value.isdigit():
        value = f"{value}.0"
    return value


def contract_version_sort_key(version):
    parts = normalize_contract_version(version).split(".")
    if all(part.isdigit() for part in parts):
        return 1, tuple(int(part) for part in parts)
    return 0, tuple(parts)


def _preferred_first(support):
    return (support.preferred_version,) + tuple(
        version
        for version in sorted(support.supported_versions, key=contract_version_sort_key, reverse=True)
        if version != support.preferred_version
    )
