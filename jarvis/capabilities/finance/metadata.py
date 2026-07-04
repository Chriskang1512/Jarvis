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
    planning_prefix="finance",
    planning_aliases=["finance", "investment", "투자", "금융"],
    planning_intents={
        "compound simulation": ["compound", "복리", "적립식", "20년", "voo"],
        "average price calculation": ["average price", "평단", "평균 단가"],
        "profit calculation": ["profit", "수익률", "손익"],
        "portfolio summary": ["portfolio", "포트폴리오", "비중"],
        "exchange conversion": ["exchange", "환율", "달러", "usd", "krw", "jpy"],
    },
    planning_examples=[
        "VOO 적립식으로 20년 계산",
        "평단 계산",
        "환율 계산",
    ],
)
