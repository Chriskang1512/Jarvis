from jarvis.capabilities.finance.metadata import FINANCE_CAPABILITY_METADATA
from jarvis.capabilities.finance.tools import (
    FinanceAveragePriceTool,
    FinanceCompoundTool,
    FinanceExchangeTool,
    FinanceProfitTool,
    FinancePortfolioTool,
)


class FinanceCapability:
    """Capability skeleton for financial workflows."""

    metadata = FINANCE_CAPABILITY_METADATA

    def get_tools(self):
        """Return tools owned by this capability."""
        return [
            FinanceCompoundTool(),
            FinanceAveragePriceTool(),
            FinanceProfitTool(),
            FinancePortfolioTool(),
            FinanceExchangeTool(),
        ]


def create_capability():
    """Create the Finance capability."""
    return FinanceCapability()
