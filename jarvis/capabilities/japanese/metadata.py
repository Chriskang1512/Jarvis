from jarvis.capabilities.metadata import CapabilityMetadata


JAPANESE_CAPABILITY_METADATA = CapabilityMetadata(
    id="japanese",
    name="Japanese",
    description="Japanese study assistant capability.",
    version="0.1.0-alpha",
    tools=[
        "japanese_translate",
        "japanese_grammar",
        "japanese_reply",
        "japanese_review",
    ],
    planning_prefix="jp",
    planning_aliases=["japanese", "jp", "일본어"],
    planning_intents={
        "translate": ["translate", "번역", "일본어로", "일본어"],
        "grammar explanation": ["grammar", "문법", "차이"],
        "reply drafting": ["reply", "답장", "아야", "유이"],
        "review": ["review", "복습"],
    },
    planning_examples=[
        "일본어로 번역",
        "일본어 문법 차이",
        "아야에게 답장",
    ],
)
