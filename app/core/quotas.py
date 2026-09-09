from typing import Final, Literal

QuotaCode = Literal[
    "memberships.max",
    "lotteries.max",
    "draws.max",
    "predictions.max",
    "ai_generations.monthly",
]

ALL_QUOTA_CODES: Final[frozenset[QuotaCode]] = frozenset(
    {
        "memberships.max",
        "lotteries.max",
        "draws.max",
        "predictions.max",
        "ai_generations.monthly",
    }
)
