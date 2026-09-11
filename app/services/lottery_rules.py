from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LotteryRules:
    main_numbers_count: int
    min_number: int
    max_number: int
    has_extra_number: bool
    extra_number_min: int | None = None
    extra_number_max: int | None = None


VERIFIED_LOTTERY_RULES: dict[str, LotteryRules] = {
    "miloto": LotteryRules(5, 1, 39, False),
    "baloto": LotteryRules(5, 1, 43, True, 1, 16),
    "revancha": LotteryRules(5, 1, 43, True, 1, 16),
}


def get_verified_lottery_rules(code: str) -> LotteryRules | None:
    return VERIFIED_LOTTERY_RULES.get(code.strip().lower())
