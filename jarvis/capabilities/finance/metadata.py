from jarvis.capabilities.metadata import CapabilityMetadata


FINANCE_CAPABILITY_METADATA = CapabilityMetadata(
    id="finance",
    name="Finance",
    description="Financial assistant capability.",
    version="0.1.0-alpha",
    status="alpha",
    owner="Jarvis Team",
    tools=[
        "finance_compound",
        "finance_average_price",
        "finance_profit",
        "finance_portfolio",
        "finance_exchange",
    ],
)
