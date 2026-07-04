import re

from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class FinancePortfolioTool:
    """Analyze a simple portfolio allocation."""

    metadata = ToolMetadata(
        name="finance_portfolio",
        description="Analyze simple portfolio allocation percentages.",
        domain="finance",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="finance",
        aliases=["finance portfolio", "portfolio analysis", "portfolio"],
        supported_intents=["portfolio allocation", "portfolio analysis", "포트폴리오 분석"],
        examples=["VOO 40% QQQ 30% 현금 30%", "finance portfolio VOO 40 QQQ 30 cash 30"],
        input_mode="text",
        input_prefixes=["finance portfolio", "portfolio analysis", "portfolio"],
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return allocation and a short diversification summary."""
        text = str(input_data.get("text", "")).strip()
        allocation = parse_allocation(input_data.get("allocation"), text)
        total = sum(allocation.values())
        normalized = normalize_allocation(allocation)
        stock_weight = sum(
            weight
            for asset, weight in normalized.items()
            if asset.lower() not in ["cash", "현금", "krw", "usd"]
        )
        cash_weight = 100 - stock_weight

        summary = "Balanced starter portfolio."
        if len(normalized) <= 1:
            summary = "Concentrated portfolio. Add more assets for diversification."
        elif stock_weight > 90:
            summary = "Growth-heavy portfolio with little cash buffer."
        elif cash_weight > 50:
            summary = "Conservative portfolio with a large cash position."

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "allocation": normalized,
                "diversification": {
                    "asset_count": len(normalized),
                    "stock_weight": round(stock_weight, 2),
                    "cash_weight": round(cash_weight, 2),
                },
                "summary": summary,
                "input_total": round(total, 2),
            },
        )


def parse_allocation(allocation, text):
    """Parse allocation from dict or free text."""
    if isinstance(allocation, dict):
        return {str(key): float(value) for key, value in allocation.items()}

    matches = re.findall(r"([A-Za-z가-힣]+)\s*(\d+(?:\.\d+)?)\s*%?", text)
    parsed = {}

    for asset, percent in matches:
        if asset.lower() in ["finance", "portfolio", "analysis"]:
            continue
        parsed[asset.upper() if asset.isascii() else asset] = float(percent)

    if len(parsed) == 0:
        return {"VOO": 40.0, "QQQ": 30.0, "CASH": 30.0}

    return parsed


def normalize_allocation(allocation):
    """Normalize allocation to 100 percent."""
    total = sum(allocation.values())
    if total == 0:
        return allocation

    return {
        asset: round(weight / total * 100, 2)
        for asset, weight in allocation.items()
    }
