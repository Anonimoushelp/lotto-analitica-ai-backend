from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LotteryRule:
    main_count: int
    main_min: int
    main_max: int
    extra_min: int | None = None
    extra_max: int | None = None


# Deliberately empty until each lottery's rules are verified against an
# authoritative source. AI predictions must fail closed rather than invent
# number domains or extra-number semantics.
VERIFIED_LOTTERY_RULES: dict[str, LotteryRule] = {}


def get_verified_lottery_rule(code: str) -> LotteryRule | None:
    return VERIFIED_LOTTERY_RULES.get(code)
