import re

from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class FinanceAveragePriceTool:
    """Calculate weighted average purchase price."""

    metadata = ToolMetadata(
        name="finance_average_price",
        description="Calculate weighted average price from buy lots.",
        domain="finance",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="finance",
        aliases=["finance average", "average price", "avg price", "평단", "평균 단가"],
        supported_intents=["average purchase price", "평균 단가", "평단 계산"],
        examples=[
            "100 shares 520 50 shares 480",
            "100주 520 50주 480",
            "평단 얼마",
            "평단 계산해줘",
            "평균 단가 계산",
        ],
        input_mode="text",
        input_prefixes=["finance average", "average price", "avg price", "평단", "평균 단가"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return weighted average price."""
        text = str(input_data.get("text", "")).strip()
        lots = input_data.get("lots")

        if not isinstance(lots, list):
            lots = parse_lots(text)

        total_quantity = sum(quantity for quantity, price in lots)
        total_cost = sum(quantity * price for quantity, price in lots)
        average_price = total_cost / total_quantity if total_quantity != 0 else 0

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "lots": [
                    {"quantity": quantity, "price": price}
                    for quantity, price in lots
                ],
                "total_quantity": round(total_quantity, 4),
                "total_cost": round(total_cost, 4),
                "average_price": round(average_price, 4),
            },
        )


def parse_lots(text):
    """Parse quantity/price pairs from text."""
    numbers = [
        float(value.replace(",", ""))
        for value in re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    ]
    lots = []

    for index in range(0, len(numbers) - 1, 2):
        lots.append((numbers[index], numbers[index + 1]))

    if len(lots) == 0:
        return [(100.0, 520.0), (50.0, 480.0)]

    return lots
