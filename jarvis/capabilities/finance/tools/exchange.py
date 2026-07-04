import re

from jarvis.permissions import PermissionLevel
from jarvis.tools import ToolMetadata, ToolResult


SAMPLE_RATES_TO_KRW = {
    "KRW": 1.0,
    "USD": 1350.0,
    "JPY": 9.1,
}


class FinanceExchangeTool:
    """Convert currencies using supplied or sample rates."""

    metadata = ToolMetadata(
        name="finance_exchange",
        description="Convert between KRW, USD, and JPY using local sample rates.",
        domain="finance",
        permission_level=PermissionLevel.SAFE,
        safety_level=PermissionLevel.SAFE,
        safe=True,
        capability="finance",
        aliases=["finance exchange", "exchange rate", "currency convert", "exchange", "환율 계산"],
        supported_intents=["currency conversion", "exchange rate", "환율 계산"],
        examples=[
            "finance exchange 100 USD KRW",
            "exchange 100 usd krw",
            "100달러 원화",
            "100달러 원화로",
            "환율 계산",
            "JPY to KRW",
        ],
        input_mode="text",
        input_prefixes=["finance exchange", "exchange rate", "currency convert", "exchange", "환율 계산"],
        allow_empty_input=True,
        route_confidence=0.78,
    )

    def execute(self, input_data):
        """Return a currency conversion."""
        text = str(input_data.get("text", "")).strip()
        amount = parse_amount(input_data.get("amount"), text)
        from_currency = normalize_currency(input_data.get("from_currency"), text, default="USD")
        to_currency = normalize_currency(input_data.get("to_currency"), text, default="KRW", skip=from_currency)
        supplied_rate = input_data.get("rate")

        if supplied_rate not in [None, ""]:
            converted = amount * float(supplied_rate)
            rate_used = float(supplied_rate)
            rate_source = "supplied"
        else:
            converted = convert_currency(amount, from_currency, to_currency)
            rate_used = converted / amount if amount != 0 else 0
            rate_source = "sample"

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output={
                "amount": round(amount, 4),
                "from": from_currency,
                "to": to_currency,
                "converted": round(converted, 4),
                "rate": round(rate_used, 6),
                "rate_source": rate_source,
            },
        )


def convert_currency(amount, from_currency, to_currency):
    """Convert via sample KRW rates."""
    krw_value = amount * SAMPLE_RATES_TO_KRW[from_currency]
    return krw_value / SAMPLE_RATES_TO_KRW[to_currency]


def parse_amount(value, text):
    """Parse amount from structured input or text."""
    if value not in [None, ""]:
        return float(str(value).replace(",", ""))

    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if match is None:
        return 1.0

    return float(match.group(0).replace(",", ""))


def normalize_currency(value, text, default, skip=None):
    """Find a supported currency code."""
    if value not in [None, ""]:
        currency = str(value).upper()
        if currency in SAMPLE_RATES_TO_KRW:
            return currency

    upper_text = text.upper()
    matches = []

    for currency in ["KRW", "USD", "JPY"]:
        if currency == skip:
            continue
        index = upper_text.find(currency)
        if index >= 0:
            matches.append((index, currency))

    if len(matches) > 0:
        return sorted(matches)[0][1]

    lowered = text.lower()
    if skip != "USD" and ("달러" in text or "dollar" in lowered):
        return "USD"
    if skip != "JPY" and ("엔" in text or "yen" in lowered):
        return "JPY"
    if skip != "KRW" and ("원" in text or "krw" in lowered):
        return "KRW"

    return default
