from collections import Counter

from app.models.lottery_draw import LotteryDraw
from sqlalchemy import select
from sqlalchemy.orm import Session


STATISTICAL_ALGORITHMS = (
    "number_frequency",
    "even_odd_distribution",
    "sum_distribution",
)


class StatisticalService:
    @staticmethod
    def analyze(draws: list[LotteryDraw]) -> dict[str, object]:
        frequency = Counter(
            number
            for draw in draws
            for number in (draw.main_numbers or [])
        )
        parity = Counter(
            f"{sum(number % 2 == 0 for number in (draw.main_numbers or []))}-"
            f"{sum(number % 2 != 0 for number in (draw.main_numbers or []))}"
            for draw in draws
        )
        sums = [
            sum(draw.main_numbers or [])
            for draw in draws
            if draw.main_numbers
        ]
        return {
            "number_frequency": dict(sorted(frequency.items())),
            "even_odd_distribution": dict(sorted(parity.items())),
            "sum_distribution": {
                "count": len(sums),
                "minimum": min(sums) if sums else None,
                "maximum": max(sums) if sums else None,
                "average": round(sum(sums) / len(sums), 2) if sums else None,
            },
        }

    @staticmethod
    def overview(db: Session) -> dict[str, int | str]:
        draws = list(db.scalars(select(LotteryDraw)).all())
        if not draws:
            return {
                "module_status": "STANDBY",
                "algorithms_count": 0,
                "draws_analyzed": 0,
            }

        StatisticalService.analyze(draws)
        return {
            "module_status": "READY",
            "algorithms_count": len(STATISTICAL_ALGORITHMS),
            "draws_analyzed": len(draws),
        }
