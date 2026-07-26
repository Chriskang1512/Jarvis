import unittest

from jarvis.abilities import (
    AbilityMetadata,
    AbilityRegistry,
    AbilityResult,
    AbilityType,
    CapabilityOperationMetadata,
)
from jarvis.permissions import PermissionLevel
from jarvis.runtime.planner import CapabilityDiscovery, RuntimePlanner
from jarvis.runtime.planner.cost import (
    AdaptiveExecutionCostModel,
    ExecutionSelectionPolicy,
)
from jarvis.tools import ToolRegistry


class PublishingAbility:
    metadata = AbilityMetadata(
        id="publishing",
        name="Publishing",
        type=AbilityType.INTEGRATION,
        permission=PermissionLevel.SAFE,
        description="Publish content through a registered provider.",
        input_schema={"text": "string"},
        output_schema={"published": "boolean"},
        capabilities=["content.publish"],
        aliases=["publisher"],
        supported_intents=["publish content", "\uac8c\uc2dc\ud574"],
        examples=["publish this", "\uc774 \uae00 \uac8c\uc2dc\ud574"],
        operations=(
            {
                "operation": "publish",
                "permission": "confirm_required",
                "side_effect": "external_write",
                "contract_version": "1.0",
                "estimated_cost": 0.2,
                "estimated_latency_ms": 80,
                "network_required": True,
            },
        ),
    )

    def execute(self, input_data):
        return AbilityResult(success=True, data={"published": True})


def create_registry():
    abilities = AbilityRegistry()
    abilities.register(PublishingAbility())
    tools = ToolRegistry()
    abilities.register_tools(tools)
    return abilities, tools


class CapabilityDiscoveryTest(unittest.TestCase):
    def test_registry_declared_operation_is_discovered(self):
        _, tools = create_registry()

        result = CapabilityDiscovery().search(
            "\uc774 \uae00 \uac8c\uc2dc\ud574",
            tools,
        )

        self.assertEqual(result.selected.operation_id, "publishing.publish")
        self.assertEqual(result.selected.permission, "confirm_required")
        self.assertEqual(result.journal[-1].decision, "SELECTED")

    def test_planner_uses_new_registry_operation_without_new_rule(self):
        _, tools = create_registry()

        plan = RuntimePlanner().plan("\uc774 \uae00 \uac8c\uc2dc\ud574", tools)

        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.steps[0].tool_name, "publishing")
        self.assertEqual(plan.steps[0].action, "publish")

    def test_unsupported_contract_is_filtered(self):
        abilities, tools = create_registry()
        operation = abilities.get_operation("publishing", "publish")
        abilities.register_operation(
            CapabilityOperationMetadata(
                **{
                    **operation.__dict__,
                    "contract_version": "99.0",
                }
            ),
            replace_existing=True,
        )

        result = CapabilityDiscovery().search(
            "\uc774 \uae00 \uac8c\uc2dc\ud574",
            tools,
            allowed_permissions={"safe"},
        )

        self.assertIsNone(result.selected)
        self.assertIn(
            "CONTRACT_VERSION_UNSUPPORTED",
            {entry.reason for entry in result.journal},
        )

    def test_permission_filter_blocks_candidate_before_planning(self):
        _, tools = create_registry()

        result = CapabilityDiscovery().search(
            "\uc774 \uae00 \uac8c\uc2dc\ud574",
            tools,
            allowed_permissions={"safe"},
        )

        self.assertIsNone(result.selected)
        self.assertIn(
            "PERMISSION_FILTERED",
            {entry.reason for entry in result.journal},
        )

    def test_offline_candidate_is_filtered(self):
        abilities, tools = create_registry()
        operation = abilities.get_operation("publishing", "publish")
        abilities.register_operation(
            CapabilityOperationMetadata(
                **{
                    **operation.__dict__,
                    "availability": "OFFLINE",
                    "health_reason": "NETWORK",
                }
            ),
            replace_existing=True,
        )

        result = CapabilityDiscovery().search(
            "\uc774 \uae00 \uac8c\uc2dc\ud574",
            tools,
        )

        self.assertIsNone(result.selected)
        self.assertIn(
            "CAPABILITY_OFFLINE",
            {entry.reason for entry in result.journal},
        )

    def test_reliability_first_optimizer_selects_best_implementation(self):
        abilities, tools = create_registry()
        base = abilities.get_operation("publishing", "publish")
        abilities.register_operation(
            CapabilityOperationMetadata(
                **{
                    **base.__dict__,
                    "reliability_score": 0.70,
                }
            ),
            replace_existing=True,
        )
        abilities.register_operation_candidate(
            CapabilityOperationMetadata(
                **{
                    **base.__dict__,
                    "implementation_id": "provider:reliable",
                    "estimated_cost": 1.0,
                    "reliability_score": 0.99,
                }
            )
        )
        abilities.register_operation_candidate(
            CapabilityOperationMetadata(
                **{
                    **base.__dict__,
                    "implementation_id": "provider:cheap",
                    "estimated_cost": 0.01,
                    "reliability_score": 0.75,
                }
            )
        )

        result = CapabilityDiscovery(
            cost_model=AdaptiveExecutionCostModel(),
            selection_policy=ExecutionSelectionPolicy(reliability_first=True),
        ).search("\uc774 \uae00 \uac8c\uc2dc\ud574", tools)

        self.assertEqual(result.selected.implementation_id, "provider:reliable")

    def test_experimental_operation_is_discoverable_with_warning(self):
        abilities, tools = create_registry()
        operation = abilities.get_operation("publishing", "publish")
        abilities.register_operation(
            CapabilityOperationMetadata(
                **{
                    **operation.__dict__,
                    "lifecycle": "experimental",
                }
            ),
            replace_existing=True,
        )

        result = CapabilityDiscovery().search(
            "\uc774 \uae00 \uac8c\uc2dc\ud574",
            tools,
        )

        self.assertIn("EXPERIMENTAL_CAPABILITY", result.selected.warnings)


if __name__ == "__main__":
    unittest.main()
