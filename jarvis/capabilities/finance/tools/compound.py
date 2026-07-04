import re

from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


class FinanceCompoundTool:
    """Simulate compound interest."""

    metadata = ToolMetadata(
        name="finance_compound",
        description="Simulate compound interest with optional monthly contribution.",
        domain="finance",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="finance",
        aliases=["finance compound", "compound interest", "compound finance", "복리 계산"],
        supported_intents=["compound interest", "finance compound simulation", "복리 계산"],
        examples=[
            "100만원을 연 7%로 20년",
            "매달 30만원 적립",
            "10년 후 얼마",
            "복리 계산",
            "finance compound",
            "finance compound 1000000 7 20 monthly 300000",
        ],
        input_mode="text",
        input_prefixes=["finance compound", "compound interest", "compound finance", "복리 계산"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a compound interest simulation."""
        text = str(input_data.get("text", "")).strip()
        principal = parse_number(input_data.get("principal"), default=None)
        annual_rate = parse_number(input_data.get("annual_rate"), default=None)
        years = parse_number(input_data.get("years"), default=None)
        monthly_contribution = parse_number(input_data.get("monthly_contribution"), default=0)

        if principal is None or annual_rate is None or years is None:
            parsed = parse_compound_text(text)
            principal = principal if principal is not None else parsed["principal"]
            annual_rate = annual_rate if annual_rate is not None else parsed["annual_rate"]
            years = years if years is not None else parsed["years"]
            monthly_contribution = parsed["monthly_contribution"]

        monthly_rate = annual_rate / 100 / 12
        months = int(years * 12)
        balance = principal

        for _ in range(months):
            balance = balance * (1 + monthly_rate) + monthly_contribution

        invested = principal + monthly_contribution * months
        gain = balance - invested

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "principal": round(principal, 2),
                "annual_rate": round(annual_rate, 4),
                "years": round(years, 2),
                "monthly_contribution": round(monthly_contribution, 2),
                "future_value": round(balance, 2),
                "total_invested": round(invested, 2),
                "estimated_gain": round(gain, 2),
            },
        )


def parse_compound_text(text):
    """Parse simple compound text into numeric assumptions."""
    numbers = [float(value.replace(",", "")) for value in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
    principal = numbers[0] if len(numbers) > 0 else 1000000
    annual_rate = numbers[1] if len(numbers) > 1 else 7
    years = numbers[2] if len(numbers) > 2 else 10
    monthly_contribution = numbers[3] if len(numbers) > 3 else 0

    if "만원" in text and principal < 10000:
        principal *= 10000

    if ("매달" in text or "monthly" in text.lower()) and len(numbers) > 3:
        monthly_contribution = numbers[3]
        if "만원" in text and monthly_contribution < 10000:
            monthly_contribution *= 10000

    return {
        "principal": principal,
        "annual_rate": annual_rate,
        "years": years,
        "monthly_contribution": monthly_contribution,
    }


def parse_number(value, default=None):
    """Parse one optional numeric value."""
    if value is None or value == "":
        return default

    return float(str(value).replace(",", ""))
