"""Trusted reproducibility metadata for planned graphs."""

from __future__ import annotations

from dataclasses import replace


class PlannerGraphMetadataEnricher:
    REQUIRED_KEYS = (
        "capabilitySnapshotId",
        "registryHash",
        "plannerType",
        "plannerVersion",
        "planningPolicyVersion",
    )

    def enrich(self, graph, request, *, planner_type, planner_version):
        metadata = dict(graph.metadata)
        metadata.update(
            {
                "capabilitySnapshotId": request.capability_snapshot.snapshot_id,
                "registryHash": request.capability_snapshot.registry_hash,
                "plannerType": str(
                    getattr(planner_type, "value", planner_type)
                ),
                "plannerVersion": str(planner_version),
                "planningPolicyVersion": str(
                    request.planning_policy.version
                ),
            }
        )
        return replace(graph, metadata=metadata)

    def matches(self, graph, request, *, planner_type, planner_version):
        expected = self.enrich(
            graph,
            request,
            planner_type=planner_type,
            planner_version=planner_version,
        ).metadata
        return all(
            graph.metadata.get(key) == expected.get(key)
            for key in self.REQUIRED_KEYS
        )


def enforce_validation_repair_version(original, repaired):
    """Require repair to preserve identity and advance one version."""
    if repaired.graph_id != original.graph_id:
        raise ValueError("Repair must preserve GraphId.")
    if repaired.version != original.version + 1:
        raise ValueError("Repair must increment Graph version by exactly one.")
    return repaired


def link_semantic_replan(original, replanned):
    """Attach lineage to a semantically new graph identity."""
    if replanned.graph_id == original.graph_id:
        raise ValueError("Semantic replan requires a new GraphId.")
    metadata = dict(replanned.metadata)
    metadata["parentGraphId"] = original.graph_id
    metadata["previousGraphVersion"] = original.version
    return replace(replanned, metadata=metadata)
