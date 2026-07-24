from collections import deque
from dataclasses import dataclass
from enum import Enum


class Availability(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class HealthReason(str, Enum):
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_FAILURE = "AUTH_FAILURE"
    NETWORK = "NETWORK"
    SERVER_ERROR = "SERVER_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RecoveryDecision:
    retry_allowed: bool
    action: str
    retry_after_seconds: int | None = None
    requires_reauthentication: bool = False


class HealthRecoveryPolicy:
    """Map stable health reasons to recovery behavior."""

    def evaluate(self, reason):
        normalized = normalize_health_reason(reason)
        decisions = {
            HealthReason.NONE: RecoveryDecision(True, "NONE", 0),
            HealthReason.TIMEOUT: RecoveryDecision(True, "RETRY_BACKOFF", 30),
            HealthReason.RATE_LIMIT: RecoveryDecision(True, "RETRY_AFTER", 300),
            HealthReason.AUTH_FAILURE: RecoveryDecision(
                False,
                "REAUTHENTICATE",
                None,
                requires_reauthentication=True,
            ),
            HealthReason.NETWORK: RecoveryDecision(False, "WAIT_FOR_NETWORK"),
            HealthReason.SERVER_ERROR: RecoveryDecision(True, "RETRY_BACKOFF", 60),
            HealthReason.UNKNOWN: RecoveryDecision(False, "REQUIRE_VERIFICATION"),
        }
        return decisions[normalized]


@dataclass(frozen=True)
class ExecutionSelectionPolicy:
    reliability_first: bool = True
    min_reliability: float = 0.0

    def __post_init__(self):
        if not 0.0 <= float(self.min_reliability) <= 1.0:
            raise ValueError("min_reliability must be between 0.0 and 1.0.")


@dataclass(frozen=True)
class EffectiveExecutionProfile:
    implementation_id: str
    estimated_cost: float
    estimated_latency_ms: int
    network_required: bool
    availability: Availability
    reliability_score: float
    metric_samples: int = 0
    health_reason: HealthReason = HealthReason.NONE


@dataclass(frozen=True)
class RuntimeMetric:
    success: bool
    latency_ms: int
    cost: float


@dataclass(frozen=True)
class ExecutionCost:
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0
    network_operations: int = 0

    def __add__(self, other):
        return ExecutionCost(
            estimated_cost=self.estimated_cost + other.estimated_cost,
            estimated_latency_ms=self.estimated_latency_ms + other.estimated_latency_ms,
            network_operations=self.network_operations + other.network_operations,
        )


def operation_cost(metadata):
    return ExecutionCost(
        estimated_cost=float(metadata.estimated_cost),
        estimated_latency_ms=int(metadata.estimated_latency_ms),
        network_operations=1 if metadata.network_required else 0,
    )


class AdaptiveExecutionCostModel:
    """Combine Registry estimates with bounded recent Runtime observations."""

    def __init__(self, window_size=20):
        self.window_size = max(1, int(window_size))
        self._metrics = {}
        self._availability = {}
        self._health_reasons = {}

    def observe(
        self,
        operation_id,
        implementation_id,
        success,
        latency_ms,
        cost=0.0,
        health_reason=HealthReason.UNKNOWN,
    ):
        key = (str(operation_id), str(implementation_id))
        samples = self._metrics.setdefault(key, deque(maxlen=self.window_size))
        samples.append(
            RuntimeMetric(
                success=bool(success),
                latency_ms=max(0, int(latency_ms)),
                cost=max(0.0, float(cost)),
            )
        )
        self._availability[key] = (
            Availability.ONLINE if success else Availability.DEGRADED
        )
        self._health_reasons[key] = (
            HealthReason.NONE if success else normalize_health_reason(health_reason)
        )

    def set_availability(
        self,
        operation_id,
        implementation_id,
        availability,
        health_reason=HealthReason.NONE,
    ):
        key = (str(operation_id), str(implementation_id))
        self._availability[key] = normalize_availability(availability)
        normalized_availability = self._availability[key]
        if normalized_availability == Availability.ONLINE:
            self._health_reasons[key] = HealthReason.NONE
        else:
            normalized_reason = normalize_health_reason(health_reason)
            self._health_reasons[key] = (
                HealthReason.UNKNOWN
                if normalized_reason == HealthReason.NONE
                else normalized_reason
            )

    def profile(self, metadata):
        key = (metadata.id, metadata.implementation_id)
        samples = tuple(self._metrics.get(key, ()))
        availability = self._availability.get(
            key,
            normalize_availability(metadata.availability),
        )
        health_reason = self._health_reasons.get(
            key,
            normalize_health_reason(metadata.health_reason),
        )
        if not samples:
            return EffectiveExecutionProfile(
                implementation_id=metadata.implementation_id,
                estimated_cost=float(metadata.estimated_cost),
                estimated_latency_ms=int(metadata.estimated_latency_ms),
                network_required=bool(metadata.network_required),
                availability=availability,
                reliability_score=float(metadata.reliability_score),
                health_reason=health_reason,
            )
        successes = sum(1 for sample in samples if sample.success)
        return EffectiveExecutionProfile(
            implementation_id=metadata.implementation_id,
            estimated_cost=sum(sample.cost for sample in samples) / len(samples),
            estimated_latency_ms=round(
                sum(sample.latency_ms for sample in samples) / len(samples)
            ),
            network_required=bool(metadata.network_required),
            availability=availability,
            reliability_score=successes / len(samples),
            metric_samples=len(samples),
            health_reason=health_reason,
        )

    def rank(self, metadata, policy):
        profile = self.profile(metadata)
        availability_rank = {
            Availability.ONLINE: 0,
            Availability.DEGRADED: 1,
            Availability.OFFLINE: 2,
        }[profile.availability]
        if policy.reliability_first:
            preference = (
                -profile.reliability_score,
                profile.estimated_cost,
            )
        else:
            preference = (
                profile.estimated_cost,
                -profile.reliability_score,
            )
        return (
            availability_rank,
            *preference,
            profile.estimated_latency_ms,
            profile.network_required,
            profile.implementation_id,
        )


def normalize_availability(value):
    if isinstance(value, Availability):
        return value
    return Availability(str(value or "").upper())


def normalize_health_reason(value):
    if isinstance(value, HealthReason):
        return value
    return HealthReason(str(value or "").upper())


def estimate_plan_cost(plan, ability_registry, cost_model=None):
    """Estimate serial plan cost using selected or default implementations."""
    total = ExecutionCost()
    for step in plan.steps:
        candidates = ability_registry.list_operation_candidates(step.capability, step.operation)
        selected = next(
            (
                item
                for item in candidates
                if step.execution_target and item.implementation_id == step.execution_target
            ),
            None,
        )
        metadata = selected or ability_registry.get_operation(step.capability, step.operation)
        if metadata is not None:
            if cost_model is None:
                total += operation_cost(metadata)
            else:
                profile = cost_model.profile(metadata)
                total += ExecutionCost(
                    estimated_cost=profile.estimated_cost,
                    estimated_latency_ms=profile.estimated_latency_ms,
                    network_operations=1 if profile.network_required else 0,
                )
    return total
