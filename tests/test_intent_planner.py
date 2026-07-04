import inspect
from pathlib import Path
import unittest

from jarvis.capabilities import CapabilityLoader, CapabilityMetadata, CapabilityRegistry
from jarvis.permissions import PermissionLevel
from jarvis.planner import IntentPlanner, PlanValidator
from jarvis.planner import intent_planner


class TestIntentPlanner(unittest.TestCase):
    """Test v0.4 Beta.1 Intent Planner contract."""

    def test_planner_contract_creation(self):
        """Check planner returns the stable top-level contract."""
        plan = create_planner().plan(
            "VOO 적립식으로 20년 계산하고 일본어로 번역해서 유튜브 설명도 만들어줘"
        ).to_dict()

        self.assertTrue(plan["plan_id"].startswith("plan_"))
        self.assertEqual(plan["planner_version"], "0.1")
        self.assertEqual(plan["graph_version"], "1.0")
        self.assertEqual(plan["status"], "CREATED")
        self.assertTrue(plan["requires_planning"])
        self.assertEqual(plan["permission_mode"], "SAFE")
        self.assertEqual(plan["execution_mode"], "sequential")
        self.assertIn("nodes", plan["graph"])
        self.assertIn("edges", plan["graph"])
        self.assertIn("metadata", plan["graph"])
        self.assertEqual(plan["graph"]["metadata"], {})

    def test_planner_selects_capabilities_not_tools(self):
        """Check planner output contains capabilities and never tool names."""
        plan = create_planner().plan(
            "VOO 적립식으로 20년 계산하고 일본어로 번역해서 유튜브 설명도 만들어줘"
        ).to_dict()
        nodes = plan["graph"]["nodes"]

        self.assertEqual([node["capability"] for node in nodes], ["finance", "japanese", "creator"])
        self.assertEqual([node["intent"] for node in nodes], ["compound simulation", "translate", "description"])
        self.assert_no_tool_references(plan)

    def test_planner_builds_required_graph_edges(self):
        """Check graph structure exists from Beta.1 even with sequential execution."""
        plan = create_planner().plan(
            "VOO 적립식으로 20년 계산하고 일본어로 번역해서 유튜브 설명도 만들어줘"
        ).to_dict()

        self.assertEqual(
            plan["graph"]["edges"],
            [
                {"id": "edge_001", "from": "finance_001", "to": "jp_002", "type": "sequential"},
                {"id": "edge_002", "from": "jp_002", "to": "creator_003", "type": "sequential"},
            ],
        )

    def test_planner_node_contract_reserves_status_required_and_confidence(self):
        """Check task nodes reserve Beta.2+ execution fields."""
        plan = create_planner().plan(
            "VOO를 20년 적립하고 일본어로 번역해서 유튜브 설명 만들어줘"
        ).to_dict()
        first_node = plan["graph"]["nodes"][0]

        self.assertEqual(first_node["id"], "finance_001")
        self.assertEqual(first_node["status"], "CREATED")
        self.assertTrue(first_node["required"])
        self.assertGreater(first_node["confidence"], 0.0)
        self.assertLessEqual(first_node["confidence"], 1.0)

    def test_planner_outputs_plan_only_for_expected_chain(self):
        """Check the PM happy path produces a plan without executing anything."""
        plan = create_planner().plan(
            "VOO를 20년 적립하고 일본어로 번역해서 유튜브 설명 만들어줘"
        ).to_dict()

        self.assertTrue(plan["requires_planning"])
        self.assertEqual([node["capability"] for node in plan["graph"]["nodes"]], ["finance", "japanese", "creator"])
        self.assertEqual([node["id"] for node in plan["graph"]["nodes"]], ["finance_001", "jp_002", "creator_003"])
        self.assertEqual(plan["status"], "CREATED")
        self.assertEqual(plan["execution_mode"], "sequential")
        self.assert_no_tool_references(plan)

    def test_hotel_multi_intent_plan(self):
        """Check one capability can appear in multiple ordered tasks."""
        plan = create_planner().plan(
            "컴플레인 리포트 작성하고 대응 매뉴얼도 만들어줘"
        ).to_dict()

        self.assertTrue(plan["requires_planning"])
        self.assertEqual([node["capability"] for node in plan["graph"]["nodes"]], ["hotel", "hotel"])
        self.assertEqual([node["intent"] for node in plan["graph"]["nodes"]], ["complaint report", "complaint manual"])

    def test_life_multi_intent_plan(self):
        """Check Life can plan todo and reflection as capability-level tasks."""
        plan = create_planner().plan("오늘 할 일 정리하고 회고도 해줘").to_dict()

        self.assertTrue(plan["requires_planning"])
        self.assertEqual([node["capability"] for node in plan["graph"]["nodes"]], ["life", "life"])
        self.assertEqual([node["intent"] for node in plan["graph"]["nodes"]], ["todo planning", "reflection"])

    def test_unknown_goal_returns_no_planning(self):
        """Check ambiguous chat falls back instead of producing a fake plan."""
        plan = create_planner().plan("안녕 자비스").to_dict()

        self.assertFalse(plan["requires_planning"])
        self.assertEqual(plan["execution_mode"], "sequential")
        self.assertEqual(plan["permission_mode"], "SAFE")
        self.assertEqual(plan["graph"]["nodes"], [])
        self.assertEqual(plan["graph"]["edges"], [])
        self.assertEqual(plan["graph"]["metadata"], {})

    def test_planner_never_imports_forbidden_core_layers(self):
        """Check Planner does not import ToolRegistry, Dispatcher, or Memory."""
        source = inspect.getsource(intent_planner)

        self.assertNotIn("jarvis.tools", source)
        self.assertNotIn("ToolRegistry", source)
        self.assertNotIn("ToolDispatcher", source)
        self.assertNotIn("jarvis.memory", source)
        self.assertNotIn("memory_store", source)

    def test_planner_never_imports_concrete_capabilities(self):
        """Check Planner does not directly import concrete capability modules."""
        source = read_planner_source()
        forbidden_imports = [
            "jarvis.capabilities.finance",
            "jarvis.capabilities.japanese",
            "jarvis.capabilities.creator",
            "jarvis.capabilities.hotel",
            "jarvis.capabilities.life",
            "FinanceCapability",
            "JapaneseCapability",
            "CreatorCapability",
            "HotelCapability",
            "LifeCapability",
        ]

        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)

    def test_planner_source_does_not_hardcode_capability_ids(self):
        """Check Planner learns capability IDs from registry metadata only."""
        source = read_planner_source()

        for capability_id in ["finance", "japanese", "creator", "hotel", "life"]:
            self.assertNotIn(f'"{capability_id}"', source)
            self.assertNotIn(f"'{capability_id}'", source)

    def test_planner_never_creates_capability_instances(self):
        """Check Planner does not instantiate capability classes directly."""
        source = read_planner_source()

        self.assertNotIn("Capability(", source)
        self.assertNotIn("create_capability(", source)

    def test_permission_mode_marks_highest_capability_permission(self):
        """Check planner marks permission mode without executing permission checks."""
        registry = CapabilityRegistry()
        registry.register(PlanningCapability("safe_cap", PermissionLevel.SAFE, {"safe intent": ["safe"]}))
        registry.register(PlanningCapability("confirm_cap", PermissionLevel.CONFIRM, {"confirm intent": ["confirm"]}))

        plan = IntentPlanner(registry).plan("safe then confirm").to_dict()

        self.assertEqual(plan["permission_mode"], "CONFIRM")

    def test_plan_validator_accepts_known_capabilities(self):
        """Check future execution can validate capability references."""
        registry = CapabilityLoader().load()
        plan = IntentPlanner(registry).plan(
            "VOO를 20년 적립하고 일본어로 번역해서 유튜브 설명 만들어줘"
        )

        result = PlanValidator(registry).validate(plan)

        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_plan_validator_rejects_unknown_capability(self):
        """Check invalid capability references are rejected before execution."""
        registry = CapabilityLoader().load()
        plan = {
            "graph": {
                "nodes": [
                    {
                        "id": "unknown_001",
                        "step": 1,
                        "capability": "unknown",
                        "intent": "unknown",
                        "input": "unknown",
                        "status": "CREATED",
                        "required": True,
                        "confidence": 0.1,
                    }
                ],
                "edges": [],
                "metadata": {},
            }
        }

        result = PlanValidator(registry).validate(plan)

        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["Unknown capability: unknown"])

    def assert_no_tool_references(self, plan):
        """Check planner contract does not leak known tool names."""
        serialized = str(plan)
        forbidden_tool_names = [
            "finance_compound",
            "japanese_translate",
            "creator_description",
            "hotel_complaint_report",
            "life_reflection",
            "'tool'",
            '"tool"',
        ]

        for tool_name in forbidden_tool_names:
            self.assertNotIn(tool_name, serialized)


class PlanningCapability:
    """Small capability stub for permission-mode planning tests."""

    def __init__(self, capability_id, permission_level, planning_intents):
        """Create a capability stub."""
        self.metadata = CapabilityMetadata(
            id=capability_id,
            name=capability_id.title(),
            description="Planning stub.",
            permission_level=permission_level,
            planning_intents=planning_intents,
        )

    def get_tools(self):
        """Planner tests do not use tools."""
        raise AssertionError("IntentPlanner must not ask capabilities for tools.")


def create_planner():
    """Create an IntentPlanner with installed capabilities."""
    return IntentPlanner(CapabilityLoader().load())


def read_planner_source():
    """Read planner source files for architecture boundary tests."""
    planner_path = Path("jarvis") / "planner"
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(planner_path.glob("*.py"))
    )


if __name__ == "__main__":
    unittest.main()
