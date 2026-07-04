class PlanValidator:
    """Validate capability-level plans before future execution."""

    def __init__(self, capability_registry):
        """Create a validator from a CapabilityRegistry."""
        self.capability_registry = capability_registry

    def validate(self, plan):
        """Return validation details for a planner contract or dictionary."""
        plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else plan
        nodes = plan_dict.get("graph", {}).get("nodes", [])
        errors = []

        for node in nodes:
            capability_id = node.get("capability", "")
            if not self.capability_registry.exists(capability_id):
                errors.append(f"Unknown capability: {capability_id}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }
