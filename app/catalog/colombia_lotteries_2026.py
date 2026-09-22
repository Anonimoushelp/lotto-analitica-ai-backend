from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LotteryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED_ORDINARY = "SUSPENDED_ORDINARY"
    EXTRAORDINARY_ONLY = "EXTRAORDINARY_ONLY"


@dataclass(frozen=True)
class ColombiaLottery2026:
    code: str
    name: str
    territory: str
    status: LotteryStatus
    ordinary_weekday: int | None
    primary_source_verified: bool = False
    source_authority: str = "CNJSA/Coljuegos"


# Python weekday: Monday=0 ... Sunday=6.
# The ordinary 2026 calendar is kept separate from exceptional
# reprogramming. Extraordinary draws must never be inferred here.
COLOMBIA_LOTTERIES_2026: tuple[ColombiaLottery2026, ...] = (
    ColombiaLottery2026("LOTERIA_CUNDINAMARCA", "Lotería de Cundinamarca", "Cundinamarca", LotteryStatus.ACTIVE, 0),
    ColombiaLottery2026("LOTERIA_TOLIMA", "Lotería del Tolima", "Tolima", LotteryStatus.ACTIVE, 0),
    ColombiaLottery2026("LOTERIA_CRUZ_ROJA", "Lotería de la Cruz Roja Colombiana", "Nacional", LotteryStatus.ACTIVE, 1),
    ColombiaLottery2026("LOTERIA_HUILA", "Lotería del Huila", "Huila", LotteryStatus.ACTIVE, 1),
    ColombiaLottery2026("LOTERIA_MANIZALES", "Lotería de Manizales", "Caldas", LotteryStatus.ACTIVE, 2),
    ColombiaLottery2026("LOTERIA_VALLE", "Lotería del Valle", "Valle del Cauca", LotteryStatus.ACTIVE, 2),
    ColombiaLottery2026("LOTERIA_META", "Lotería del Meta", "Meta", LotteryStatus.ACTIVE, 2),
    ColombiaLottery2026("LOTERIA_BOGOTA", "Lotería de Bogotá", "Bogotá D.C.", LotteryStatus.ACTIVE, 3),
    ColombiaLottery2026("LOTERIA_QUINDIO", "Lotería del Quindío", "Quindío", LotteryStatus.SUSPENDED_ORDINARY, 3),
    ColombiaLottery2026("LOTERIA_MEDELLIN", "Lotería de Medellín", "Antioquia", LotteryStatus.ACTIVE, 4),
    ColombiaLottery2026("LOTERIA_SANTANDER", "Lotería de Santander", "Santander", LotteryStatus.ACTIVE, 4),
    ColombiaLottery2026("LOTERIA_RISARALDA", "Lotería de Risaralda", "Risaralda", LotteryStatus.ACTIVE, 4),
    ColombiaLottery2026("LOTERIA_BOYACA", "Lotería de Boyacá", "Boyacá", LotteryStatus.ACTIVE, 5),
    ColombiaLottery2026("LOTERIA_CAUCA", "Lotería del Cauca", "Cauca", LotteryStatus.ACTIVE, 5),
    ColombiaLottery2026("EXTRA_COLOMBIA", "Extra de Colombia", "Nacional", LotteryStatus.EXTRAORDINARY_ONLY, None),
)


def get_colombia_lottery(code: str) -> ColombiaLottery2026:
    normalized = code.strip().upper()
    for lottery in COLOMBIA_LOTTERIES_2026:
        if lottery.code == normalized:
            return lottery
    raise KeyError(f"Unknown Colombia lottery: {code}")


def active_ordinary_lotteries() -> tuple[ColombiaLottery2026, ...]:
    return tuple(
        lottery
        for lottery in COLOMBIA_LOTTERIES_2026
        if lottery.status is LotteryStatus.ACTIVE
    )
