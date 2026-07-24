from collections import deque
from dataclasses import dataclass
from datetime import date, datetime


class ContractNegotiationError(ValueError):
    """Fail-closed contract negotiation error with a stable code."""

    def __init__(self, code, message="", details=()):
        self.code = code
        self.details = tuple(details)
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
    capability_issues: tuple[object, ...] = ()

    @property
    def direct(self):
        return not self.adapter_names


@dataclass(frozen=True)
class CapabilityVersionRequirement:
    """Minimum and recommended contract versions for one operation."""

    capability: str
    min_contract: str
    recommended: str = ""
    deprecated_after: str = ""
    sunset: str = ""

    def __post_init__(self):
        minimum = normalize_contract_version(self.min_contract)
        recommended = normalize_contract_version(self.recommended) if self.recommended else minimum
        deprecated_after = (
            normalize_contract_version(self.deprecated_after)
            if self.deprecated_after
            else ""
        )
        sunset = normalize_sunset_date(self.sunset) if self.sunset else ""
        if compare_contract_versions(recommended, minimum) < 0:
            raise ContractNegotiationError("CAPABILITY_RECOMMENDED_BELOW_MINIMUM")
        if deprecated_after and compare_contract_versions(deprecated_after, minimum) < 0:
            raise ContractNegotiationError("CAPABILITY_DEPRECATION_BELOW_MINIMUM")
        object.__setattr__(self, "capability", str(self.capability or "").strip())
        object.__setattr__(self, "min_contract", minimum)
        object.__setattr__(self, "recommended", recommended)
        object.__setattr__(self, "deprecated_after", deprecated_after)
        object.__setattr__(self, "sunset", sunset)
        if not self.capability:
            raise ContractNegotiationError("CAPABILITY_REQUIRED")


@dataclass(frozen=True)
class CapabilityCompatibilityIssue:
    code: str
    capability: str
    selected_version: str
    required_version: str
    severity: str


@dataclass(frozen=True)
class CapabilityCompatibilityResult:
    issues: tuple[CapabilityCompatibilityIssue, ...] = ()

    @property
    def compatible(self):
        return not any(issue.severity == "error" for issue in self.issues)


class CapabilityVersionRegistry:
    """Store operation-level contract version requirements."""

    def __init__(self):
        self._requirements = {}

    def register(self, requirement):
        if requirement.capability in self._requirements:
            raise ContractNegotiationError("CAPABILITY_VERSION_ALREADY_REGISTERED")
        self._requirements[requirement.capability] = requirement

    def get(self, capability):
        return self._requirements.get(str(capability or "").strip())

    def validate(self, selected_version, capabilities, current_date=None):
        selected = normalize_contract_version(selected_version)
        today = normalize_current_date(current_date)
        issues = []
        for capability in tuple(dict.fromkeys(str(item or "").strip() for item in capabilities)):
            requirement = self.get(capability)
            if requirement is None:
                continue
            if compare_contract_versions(selected, requirement.min_contract) < 0:
                issues.append(
                    CapabilityCompatibilityIssue(
                        "CAPABILITY_CONTRACT_VERSION_UNSUPPORTED",
                        capability,
                        selected,
                        requirement.min_contract,
                        "error",
                    )
                )
            elif compare_contract_versions(selected, requirement.recommended) < 0:
                issues.append(
                    CapabilityCompatibilityIssue(
                        "CAPABILITY_CONTRACT_VERSION_BELOW_RECOMMENDED",
                        capability,
                        selected,
                        requirement.recommended,
                        "warning",
                    )
                )
            if (
                requirement.deprecated_after
                and compare_contract_versions(selected, requirement.deprecated_after) > 0
            ):
                issues.append(
                    CapabilityCompatibilityIssue(
                        "CAPABILITY_CONTRACT_DEPRECATED",
                        capability,
                        selected,
                        requirement.deprecated_after,
                        "warning",
                    )
                )
            if requirement.sunset:
                sunset_date = date.fromisoformat(requirement.sunset)
                if today >= sunset_date:
                    issues.append(
                        CapabilityCompatibilityIssue(
                            "CAPABILITY_SUNSET_REACHED",
                            capability,
                            selected,
                            requirement.sunset,
                            "error",
                        )
                    )
                else:
                    issues.append(
                        CapabilityCompatibilityIssue(
                            "CAPABILITY_SUNSET_SCHEDULED",
                            capability,
                            selected,
                            requirement.sunset,
                            "warning",
                        )
                    )
        return CapabilityCompatibilityResult(tuple(issues))


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

    def __init__(self, adapter_registry=None, capability_registry=None, today_provider=None):
        self.adapter_registry = adapter_registry or VersionAdapterRegistry()
        self.capability_registry = capability_registry or CapabilityVersionRegistry()
        self.today_provider = today_provider or date.today

    def negotiate(self, producer, consumer, capabilities=()):
        common = set(producer.supported_versions) & set(consumer.supported_versions)
        if common:
            selected = max(common, key=contract_version_sort_key)
            return self._check_capabilities(ContractNegotiationResult(selected, selected), capabilities)

        producer_versions = _preferred_first(producer)
        for source in producer_versions:
            path = self.adapter_registry.find_path(source, consumer.supported_versions)
            if path:
                result = ContractNegotiationResult(
                    producer_version=source,
                    selected_version=path[-1].to_version,
                    adapter_names=tuple(adapter.name for adapter in path),
                )
                return self._check_capabilities(result, capabilities)
        raise ContractNegotiationError(
            "CONTRACT_VERSION_NOT_NEGOTIABLE",
            f"{producer.component} and {consumer.component} have no compatible contract version.",
        )

    def negotiate_plan(self, producer, consumer, plan):
        """Negotiate and validate every capability operation in an AgentPlan."""
        capabilities = tuple(
            f"{step.capability}.{step.operation}" if step.operation else step.capability
            for step in plan.steps
        )
        return self.negotiate(producer, consumer, capabilities=capabilities)

    def _check_capabilities(self, result, capabilities):
        compatibility = self.capability_registry.validate(
            result.selected_version,
            capabilities,
            current_date=self.today_provider(),
        )
        if not compatibility.compatible:
            first_error = next(issue for issue in compatibility.issues if issue.severity == "error")
            raise ContractNegotiationError(
                first_error.code,
                "The negotiated contract version does not support every requested capability.",
                details=compatibility.issues,
            )
        return ContractNegotiationResult(
            producer_version=result.producer_version,
            selected_version=result.selected_version,
            adapter_names=result.adapter_names,
            capability_issues=compatibility.issues,
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


def compare_contract_versions(left, right):
    left_key = contract_version_sort_key(left)
    right_key = contract_version_sort_key(right)
    if left_key < right_key:
        return -1
    if left_key > right_key:
        return 1
    return 0


def normalize_sunset_date(value):
    """Normalize YYYY-MM or YYYY-MM-DD lifecycle dates."""
    text = str(value or "").strip()
    try:
        if len(text) == 7:
            return datetime.strptime(text, "%Y-%m").date().replace(day=1).isoformat()
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ContractNegotiationError("CAPABILITY_SUNSET_INVALID") from error


def normalize_current_date(value):
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ContractNegotiationError("CURRENT_DATE_INVALID") from error


def _preferred_first(support):
    return (support.preferred_version,) + tuple(
        version
        for version in sorted(support.supported_versions, key=contract_version_sort_key, reverse=True)
        if version != support.preferred_version
    )
