import re

from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class FinanceProfitTool:
    """Calculate profit, return rate, and after-tax profit."""

    metadata = ToolMetadata(
        name="finance_profit",
        description="Calculate profit/loss, return rate, and after-tax result.",
        domain="finance",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="finance",
        aliases=["finance profit", "profit calculator", "profit loss", "수익률 계산", "손익 계산"],
        supported_intents=["profit loss", "return rate", "세후 계산", "손익 계산", "수익률 계산"],
        examples=[
            "buy 520 sell 600 qty 100 tax 15.4",
            "매수가 520 매도가 600 100주",
            "세후 손익",
            "수익률 계산",
            "손익 계산",
            "세후 계산",
        ],
        input_mode="text",
        input_prefixes=["finance profit", "profit calculator", "profit loss", "수익률 계산", "손익 계산", "세후 계산"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return profit/loss calculation."""
        text = str(input_data.get("text", "")).strip()
        numbers = parse_numbers(text)
        buy_price = parse_value(input_data.get("buy_price"), numbers, 0, 100)
        sell_price = parse_value(input_data.get("sell_price"), numbers, 1, 120)
        quantity = parse_value(input_data.get("quantity"), numbers, 2, 1)
        tax_rate = parse_value(input_data.get("tax_rate"), numbers, 3, 15.4)
        gross_profit = (sell_price - buy_price) * quantity
        return_rate = (sell_price - buy_price) / buy_price * 100 if buy_price != 0 else 0
        after_tax_profit = gross_profit * (1 - tax_rate / 100) if gross_profit > 0 else gross_profit

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "buy_price": round(buy_price, 4),
                "sell_price": round(sell_price, 4),
                "quantity": round(quantity, 4),
                "gross_profit": round(gross_profit, 4),
                "return_rate": round(return_rate, 4),
                "tax_rate": round(tax_rate, 4),
                "after_tax_profit": round(after_tax_profit, 4),
            },
        )


def parse_value(value, numbers, index, default):
    """Parse structured value or fallback numeric index."""
    if value not in [None, ""]:
        return float(str(value).replace(",", ""))

    if len(numbers) > index:
        return numbers[index]

    return default


def parse_numbers(text):
    """Extract numeric values from text."""
    return [
        float(value.replace(",", ""))
        for value in re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    ]
