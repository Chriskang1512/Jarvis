from dataclasses import dataclass


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


def estimate_plan_cost(plan, ability_registry):
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
            total += operation_cost(metadata)
    return total
