"""Capability-aware planning foundation for Jarvis v1.4."""

from jarvis.capability_planning.ai_planner import AIPlanner
from jarvis.capability_planning.hybrid import HybridPlanner
from jarvis.capability_planning.diagnostics import PlannerDiagnosticsSanitizer
from jarvis.capability_planning.execution_snapshot import (
    ExecutionPlanSnapshot,
    ExecutionPlanSnapshotFactory,
    SnapshotVerificationIssue,
    SnapshotVerificationResult,
    SnapshotVerifier,
)
from jarvis.capability_planning.models import *
from jarvis.capability_planning.metadata import (
    PlannerGraphMetadataEnricher,
    enforce_validation_repair_version,
    link_semantic_replan,
)
from jarvis.capability_planning.registry import (
    CapabilityRegistryAdapter,
    create_system_descriptors,
)
from jarvis.capability_planning.rule_planner import RulePlanner
from jarvis.capability_planning.runtime import (
    NativePlanningCoordinator,
    NativePlanningOutcome,
)
from jarvis.capability_planning.serialization import (
    planner_result_from_json,
    planner_result_to_json,
    snapshot_from_json,
    snapshot_to_json,
)
from jarvis.capability_planning.shadow import (
    ExecutionPlanShadowComparer,
    ShadowComparisonResult,
)
from jarvis.capability_planning.validation import CapabilityPlanValidator

__all__ = [
    "AIPlanner",
    "Assumption",
    "Availability",
    "CapabilityDescriptor",
    "CapabilityInputDefinition",
    "CapabilityOutputDefinition",
    "CapabilityPlanValidator",
    "CapabilityRegistryAdapter",
    "CapabilityRegistrySnapshot",
    "DisabledCapability",
    "ExecutionCharacteristics",
    "ExecutionPlanSnapshot",
    "ExecutionPlanSnapshotFactory",
    "SnapshotVerificationIssue",
    "SnapshotVerificationResult",
    "SnapshotVerifier",
    "ExecutionPlanShadowComparer",
    "HybridPlanner",
    "MissingInput",
    "NativePlanningCoordinator",
    "NativePlanningOutcome",
    "PlannerDiagnostics",
    "PlannerDiagnosticsSanitizer",
    "PlannerFailure",
    "PlannerFailureReason",
    "PlannerGraphMetadataEnricher",
    "PlannerRequest",
    "PlannerResult",
    "PlannerStatus",
    "PlannerType",
    "PlanningPolicy",
    "ProviderRequirements",
    "RulePlanner",
    "ShadowComparisonResult",
    "SuccessCriterionMapping",
    "VerificationSupport",
    "create_system_descriptors",
    "planner_result_from_json",
    "planner_result_to_json",
    "snapshot_from_json",
    "snapshot_to_json",
    "enforce_validation_repair_version",
    "link_semantic_replan",
]
