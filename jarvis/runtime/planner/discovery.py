from dataclasses import dataclass, field

from jarvis.runtime.planner.contracts import CONTRACT_VERSION
from jarvis.runtime.planner.cost import (
    AdaptiveExecutionCostModel,
    Availability,
    ExecutionSelectionPolicy,
)
from jarvis.runtime.planner.versioning import compare_contract_versions
from jarvis.tools.router import select_candidate


OPERATION_TERMS = {
    "list": ("list", "show", "recent", "\ubaa9\ub85d", "\ucd5c\uadfc", "\uc54c\ub824", "\uc870\ud68c"),
    "get": ("get", "read", "detail", "\uc77d\uc5b4", "\ubc88\ud638", "\uc0c1\uc138"),
    "search": ("search", "find", "\ucc3e\uc544", "\uac80\uc0c9"),
    "query": ("query", "weather", "\ub0a0\uc528", "\uc870\ud68c", "\uc54c\ub824"),
    "create": ("create", "add", "register", "\ub9cc\ub4e4", "\ucd94\uac00", "\ub4f1\ub85d", "\uc7a1\uc544"),
    "update": ("update", "edit", "change", "\uc218\uc815", "\ubcc0\uacbd"),
    "delete": ("delete", "remove", "\uc0ad\uc81c", "\uc9c0\uc6cc"),
    "send": ("send", "\ubcf4\ub0b4", "\uc804\uc1a1"),
    "reply": ("reply", "\ub2f5\uc7a5"),
    "publish": ("publish", "\uac8c\uc2dc", "\ubc1c\ud589"),
    "remember": ("remember", "\uae30\uc5b5"),
    "recall": ("recall", "\uae30\uc5b5", "\ubb50\uc600"),
    "cancel": ("cancel", "\ucde8\uc18c"),
    "complete": ("complete", "\uc644\ub8cc"),
}


@dataclass(frozen=True)
class CapabilityCandidate:
    operation_id: str
    capability: str
    operation: str
    tool_name: str
    implementation_id: str
    confidence: float
    permission: str
    contract_version: str
    lifecycle: str
    side_effect: str
    estimated_cost: float
    estimated_latency_ms: int
    availability: str
    reliability_score: float
    input_data: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveryJournalEntry:
    operation_id: str
    implementation_id: str
    decision: str
    reason: str
    confidence: float = 0.0


@dataclass(frozen=True)
class CapabilityDiscoveryResult:
    goal: str
    candidates: tuple[CapabilityCandidate, ...] = ()
    journal: tuple[DiscoveryJournalEntry, ...] = ()

    @property
    def selected(self):
        return self.candidates[0] if self.candidates else None


class CapabilityDiscovery:
    """Discover execution operations from Registry metadata and Runtime policy."""

    def __init__(
        self,
        contract_version=CONTRACT_VERSION,
        cost_model=None,
        selection_policy=None,
    ):
        self.contract_version = contract_version
        self.cost_model = cost_model or AdaptiveExecutionCostModel()
        self.selection_policy = selection_policy or ExecutionSelectionPolicy()
        self.last_result = CapabilityDiscoveryResult("")

    def search(self, goal, registry, allowed_permissions=None):
        text = str(goal or "").strip()
        ability_registry = getattr(registry, "ability_registry", None)
        if not text or ability_registry is None:
            self.last_result = CapabilityDiscoveryResult(text)
            return self.last_result

        allowed = set(allowed_permissions or ("safe", "confirm_required"))
        candidates = []
        journal = []
        tools = {tool.metadata.name: tool for tool in registry.list()}

        for primary in ability_registry.list_operations():
            implementations = ability_registry.list_operation_candidates(
                primary.capability,
                primary.operation,
            ) or (primary,)
            for metadata in implementations:
                self._consider(
                    text,
                    metadata,
                    tools.get(metadata.capability),
                    allowed,
                    candidates,
                    journal,
                )

        candidates.sort(
            key=lambda item: candidate_rank(
                item,
                ability_registry,
                self.cost_model,
                self.selection_policy,
            )
        )
        if candidates:
            winner = candidates[0]
            journal.append(
                DiscoveryJournalEntry(
                    winner.operation_id,
                    winner.implementation_id,
                    "SELECTED",
                    "BEST_POLICY_SCORE",
                    winner.confidence,
                )
            )
        self.last_result = CapabilityDiscoveryResult(
            text,
            tuple(candidates),
            tuple(journal),
        )
        return self.last_result

    def _consider(self, text, metadata, tool, allowed, candidates, journal):
        if tool is None:
            journal.append(rejected(metadata, "TOOL_NOT_REGISTERED"))
            return

        route = select_candidate(tool, text)
        confidence = discovery_confidence(text, metadata.operation, route)
        if confidence <= 0:
            journal.append(rejected(metadata, "GOAL_NOT_MATCHED"))
            return

        reason = contract_rejection(
            metadata,
            self.contract_version,
            allowed,
            self.cost_model,
        )
        if reason:
            journal.append(rejected(metadata, reason, confidence))
            return

        profile = self.cost_model.profile(metadata)
        candidates.append(
            CapabilityCandidate(
                operation_id=metadata.id,
                capability=metadata.capability,
                operation=metadata.operation,
                tool_name=tool.metadata.name,
                implementation_id=metadata.implementation_id,
                confidence=confidence,
                permission=metadata.permission,
                contract_version=metadata.contract_version,
                lifecycle=metadata.lifecycle,
                side_effect=metadata.side_effect,
                estimated_cost=profile.estimated_cost,
                estimated_latency_ms=profile.estimated_latency_ms,
                availability=profile.availability.value,
                reliability_score=profile.reliability_score,
                input_data=dict(route["input_data"]) if route else {"text": text},
                warnings=lifecycle_warnings(metadata.lifecycle),
            )
        )
        journal.append(
            DiscoveryJournalEntry(
                metadata.id,
                metadata.implementation_id,
                "CANDIDATE",
                "POLICY_MATCHED",
                confidence,
            )
        )


def discovery_confidence(text, operation, route):
    normalized = str(text or "").lower()
    route_score = float(route["confidence"]) if route else 0.0
    terms = OPERATION_TERMS.get(
        str(operation).lower(),
        (str(operation).lower(),),
    )
    action_match = any(term and term in normalized for term in terms)
    if not route and not action_match:
        return 0.0
    if action_match:
        return min(1.0, max(route_score, 0.72) + 0.12)
    return max(0.0, route_score - 0.18)


def contract_rejection(metadata, runtime_version, allowed_permissions, cost_model):
    if compare_contract_versions(runtime_version, metadata.contract_version) < 0:
        return "CONTRACT_VERSION_UNSUPPORTED"
    lifecycle = str(metadata.lifecycle or "stable").lower()
    if lifecycle == "sunset":
        return "CAPABILITY_SUNSET"
    if metadata.permission not in allowed_permissions:
        return "PERMISSION_FILTERED"
    if cost_model.profile(metadata).availability == Availability.OFFLINE:
        return "CAPABILITY_OFFLINE"
    return ""


def lifecycle_warnings(lifecycle):
    normalized = str(lifecycle or "stable").lower()
    if normalized == "experimental":
        return ("EXPERIMENTAL_CAPABILITY",)
    if normalized == "deprecated":
        return ("DEPRECATED_CAPABILITY",)
    return ()


def candidate_rank(candidate, registry, cost_model, policy):
    implementations = registry.list_operation_candidates(
        candidate.capability,
        candidate.operation,
    )
    metadata = next(
        (
            item
            for item in implementations
            if item.implementation_id == candidate.implementation_id
        ),
        registry.get_operation(candidate.capability, candidate.operation),
    )
    return (-candidate.confidence, *cost_model.rank(metadata, policy))


def rejected(metadata, reason, confidence=0.0):
    return DiscoveryJournalEntry(
        metadata.id,
        metadata.implementation_id,
        "REJECTED",
        reason,
        confidence,
    )
