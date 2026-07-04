import unittest

from jarvis.brain import BrainToolRouter
from jarvis.capabilities import CapabilityLoader
from jarvis.tools import ToolDispatcher, ToolRequest, create_default_tool_registry
from jarvis.tools.registry import ToolRegistry


class TestFinanceCapability(unittest.TestCase):
    """Test Finance Capability Alpha."""

    def test_finance_capability_is_discovered(self):
        """Check the Finance capability is discovered by the loader."""
        registry = CapabilityLoader().load()

        self.assertTrue(registry.exists("finance"))

    def test_finance_tools_are_registered(self):
        """Check Finance capability registers all alpha tools."""
        capability_registry = CapabilityLoader().load()
        tool_registry = ToolRegistry()
        capability_registry.register_tools(tool_registry)

        self.assertTrue(tool_registry.exists("finance_compound"))
        self.assertTrue(tool_registry.exists("finance_average_price"))
        self.assertTrue(tool_registry.exists("finance_profit"))
        self.assertTrue(tool_registry.exists("finance_portfolio"))
        self.assertTrue(tool_registry.exists("finance_exchange"))

    def test_brain_routes_compound_request(self):
        """Check Brain routes compound requests through registry metadata."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan(
            "finance compound 1000000 7 20 monthly 300000",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "finance_compound")

    def test_brain_routes_bare_compound_request(self):
        """Check bare finance compound request routes with default assumptions."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan("finance compound", registry=tool_registry)

        self.assertEqual(request.tool_name, "finance_compound")

    def test_brain_routes_portfolio_request(self):
        """Check Brain routes portfolio requests through registry metadata."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan(
            "finance portfolio VOO 40 QQQ 30 cash 30",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "finance_portfolio")

    def test_brain_routes_average_price_request(self):
        """Check Brain routes average price requests through registry metadata."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan(
            "average price 100 520 50 480",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "finance_average_price")

    def test_brain_routes_korean_average_price_request(self):
        """Check Korean average price request routes to Finance."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan("평단 계산해줘", registry=tool_registry)

        self.assertEqual(request.tool_name, "finance_average_price")

    def test_brain_routes_profit_request(self):
        """Check Brain routes profit requests through registry metadata."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan(
            "finance profit 520 600 100",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "finance_profit")

    def test_brain_routes_exchange_request(self):
        """Check Brain routes exchange requests through registry metadata."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan(
            "finance exchange 100 USD KRW",
            registry=tool_registry,
        )

        self.assertEqual(request.tool_name, "finance_exchange")

    def test_brain_routes_short_exchange_request(self):
        """Check short exchange request routes to Finance."""
        tool_registry = create_finance_tool_registry()
        request = BrainToolRouter().plan("exchange 100 usd krw", registry=tool_registry)

        self.assertEqual(request.tool_name, "finance_exchange")

    def test_compound_tool_returns_simulation(self):
        """Check compound tool returns future value fields."""
        dispatcher = ToolDispatcher(registry=create_finance_tool_registry())
        result = dispatcher.execute(
            ToolRequest(
                tool_name="finance_compound",
                input_data={"text": "1000000 7 20 monthly 300000"},
            )
        )

        self.assertTrue(result.success)
        self.assertIn("future_value", result.output)
        self.assertGreater(result.output["future_value"], 1000000)

    def test_average_price_tool_returns_weighted_average(self):
        """Check average price tool calculates weighted average."""
        dispatcher = ToolDispatcher(registry=create_finance_tool_registry())
        result = dispatcher.execute(
            ToolRequest(
                tool_name="finance_average_price",
                input_data={"text": "100 520 50 480"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["total_quantity"], 150.0)
        self.assertAlmostEqual(result.output["average_price"], 506.6667)

    def test_profit_tool_returns_after_tax_profit(self):
        """Check profit tool calculates return and after-tax profit."""
        dispatcher = ToolDispatcher(registry=create_finance_tool_registry())
        result = dispatcher.execute(
            ToolRequest(
                tool_name="finance_profit",
                input_data={"text": "520 600 100 15.4"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["gross_profit"], 8000.0)
        self.assertAlmostEqual(result.output["return_rate"], 15.3846)
        self.assertEqual(result.output["after_tax_profit"], 6768.0)

    def test_portfolio_tool_returns_allocation_summary(self):
        """Check portfolio tool returns allocation and diversification."""
        dispatcher = ToolDispatcher(registry=create_finance_tool_registry())
        result = dispatcher.execute(
            ToolRequest(
                tool_name="finance_portfolio",
                input_data={"text": "VOO 40 QQQ 30 cash 30"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["allocation"]["VOO"], 40.0)
        self.assertIn("diversification", result.output)
        self.assertIn("summary", result.output)

    def test_exchange_tool_converts_sample_rate(self):
        """Check exchange tool converts supported currencies."""
        dispatcher = ToolDispatcher(registry=create_finance_tool_registry())
        result = dispatcher.execute(
            ToolRequest(
                tool_name="finance_exchange",
                input_data={"text": "100 USD KRW"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["from"], "USD")
        self.assertEqual(result.output["to"], "KRW")
        self.assertEqual(result.output["rate_source"], "sample")

    def test_existing_japanese_routing_still_passes(self):
        """Check Japanese routing still works with Finance installed."""
        tool_registry = ToolRegistry()
        capability_registry = CapabilityLoader().load()
        capability_registry.register_tools(tool_registry)
        request = BrainToolRouter().plan("reply to aya", registry=tool_registry)

        self.assertEqual(request.tool_name, "japanese_reply")

    def test_existing_core_routes_still_pass_with_finance_capability(self):
        """Check calculator, time, and diagnostics routes still work."""
        tool_registry = create_default_tool_registry()
        capability_registry = CapabilityLoader().load()
        capability_registry.register_tools(tool_registry)
        router = BrainToolRouter()

        self.assertEqual(
            router.plan("calculate 2 + 2", registry=tool_registry).tool_name,
            "calculator",
        )
        self.assertEqual(
            router.plan("what time is it", registry=tool_registry).tool_name,
            "time",
        )
        self.assertEqual(
            router.plan("health check", registry=tool_registry).tool_name,
            "diagnostics",
        )


def create_finance_tool_registry():
    """Create a ToolRegistry with Finance capability tools."""
    capability_registry = CapabilityLoader().load()
    tool_registry = ToolRegistry()
    capability_registry.register_tools(tool_registry)
    return tool_registry


if __name__ == "__main__":
    unittest.main()
