import unittest

from jarvis.brain import BrainToolRouter
from jarvis.capabilities import CapabilityLoader
from jarvis.tools import ToolDispatcher, ToolRequest, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry


class TestHotelCapability(unittest.TestCase):
    """Test Hotel Capability Alpha."""

    def test_hotel_capability_is_discovered(self):
        """Check the Hotel capability is discovered by the loader."""
        registry = CapabilityLoader().load()

        self.assertTrue(registry.exists("hotel"))

    def test_hotel_tools_are_registered(self):
        """Check Hotel capability registers all alpha tools."""
        capability_registry = CapabilityLoader().load()
        tool_registry = ToolRegistry()
        capability_registry.register_tools(tool_registry)

        self.assertTrue(tool_registry.exists("hotel_schedule_planner"))
        self.assertTrue(tool_registry.exists("hotel_complaint_report"))
        self.assertTrue(tool_registry.exists("hotel_complaint_manual"))

    def test_brain_routes_schedule_planner_request(self):
        """Check Brain routes Hotel schedule requests through metadata."""
        request = BrainToolRouter().plan(
            "호텔 스케줄 짜줘",
            registry=create_hotel_tool_registry(),
        )

        self.assertEqual(request.tool_name, "hotel_schedule_planner")

    def test_brain_routes_front_schedule_request(self):
        """Check Brain routes front office schedule requests."""
        request = BrainToolRouter().plan(
            "프론트 근무표 만들어줘",
            registry=create_hotel_tool_registry(),
        )

        self.assertEqual(request.tool_name, "hotel_schedule_planner")

    def test_brain_routes_complaint_report_request(self):
        """Check Brain routes complaint report requests."""
        request = BrainToolRouter().plan(
            "컴플레인 리포트 작성해줘",
            registry=create_hotel_tool_registry(),
        )

        self.assertEqual(request.tool_name, "hotel_complaint_report")

    def test_brain_routes_complaint_manual_request(self):
        """Check Brain routes complaint manual requests."""
        request = BrainToolRouter().plan(
            "소음 컴플레인 대응 매뉴얼",
            registry=create_hotel_tool_registry(),
        )

        self.assertEqual(request.tool_name, "hotel_complaint_manual")

    def test_schedule_planner_returns_contract(self):
        """Check schedule planner returns draft, conflicts, and notes."""
        result = ToolDispatcher(registry=create_hotel_tool_registry()).execute(
            ToolRequest(
                tool_name="hotel_schedule_planner",
                input_data={
                    "text": "직원 휴무 반영해서 스케줄 만들어줘",
                    "staff": ["민경", "도현", "예주"],
                    "requests": ["민경 6/10 OFF"],
                    "constraints": ["야간 다음날 D 근무 금지", "A와 B는 같은 조 배치 금지"],
                },
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["tool"], "hotel_schedule_planner")
        self.assertIn("staff", result.output)
        self.assertIn("schedule_codes", result.output)
        self.assertIn("draft_schedule", result.output)
        self.assertIn("conflicts", result.output)
        self.assertIn("notes", result.output)
        self.assertGreater(len(result.output["conflicts"]), 0)

    def test_complaint_report_returns_contract(self):
        """Check complaint report returns manager report fields."""
        result = ToolDispatcher(registry=create_hotel_tool_registry()).execute(
            ToolRequest(
                tool_name="hotel_complaint_report",
                input_data={"text": "객실 소음 컴플레인 보고서 1208"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["tool"], "hotel_complaint_report")
        self.assertIn("summary", result.output)
        self.assertIn("timeline", result.output)
        self.assertIn("guest_claim", result.output)
        self.assertIn("manager_report", result.output)

    def test_complaint_manual_returns_contract(self):
        """Check complaint manual returns SOP fields."""
        result = ToolDispatcher(registry=create_hotel_tool_registry()).execute(
            ToolRequest(
                tool_name="hotel_complaint_manual",
                input_data={"text": "환불 요구 고객 대응법"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["tool"], "hotel_complaint_manual")
        self.assertIn("first_response", result.output)
        self.assertIn("do", result.output)
        self.assertIn("dont", result.output)
        self.assertIn("escalation 기준", result.output)
        self.assertIn("sample_script", result.output)

    def test_existing_capability_and_core_routes_still_pass(self):
        """Check Hotel does not break Japanese, Finance, Creator, or Core."""
        tool_registry = create_default_tool_registry()
        capability_registry = CapabilityLoader().load()
        capability_registry.register_tools(tool_registry)
        router = BrainToolRouter()

        self.assertEqual(router.plan("reply to aya", registry=tool_registry).tool_name, "japanese_reply")
        self.assertEqual(router.plan("finance compound", registry=tool_registry).tool_name, "finance_compound")
        self.assertEqual(router.plan("song package", registry=tool_registry).tool_name, "creator_song_package")
        self.assertEqual(router.plan("calculate 2 + 2", registry=tool_registry).tool_name, "calculator")
        self.assertEqual(router.plan("what time is it", registry=tool_registry).tool_name, "time")


def create_hotel_tool_registry():
    """Create a ToolRegistry with Hotel capability tools."""
    capability_registry = CapabilityLoader().load()
    tool_registry = ToolRegistry()
    capability_registry.register_tools(tool_registry)
    return tool_registry


if __name__ == "__main__":
    unittest.main()
