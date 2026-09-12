import collections
import itertools
from datetime import date
from numbers import Integral

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lottery_draw import LotteryDraw


STATISTICAL_ALGORITHMS = (
    "number_frequency",
    "number_recency",
    "even_odd_distribution",
    "sum_distribution",
    "pair_frequency",
    "consecutive_numbers",
)


class StatisticalService:
    @staticmethod
    def _validate_draws(draws: list[LotteryDraw]) -> None:
        if not isinstance(draws, list):
            raise TypeError("Statistical analysis requires a list of draws")

        for draw in draws:
            draw_date = getattr(draw, "draw_date", None)
            if not isinstance(draw_date, date):
                raise TypeError("Each draw must have a valid draw_date")

            main_numbers = getattr(draw, "main_numbers", None)
            if main_numbers is None:
                continue
            if not isinstance(main_numbers, list):
                raise TypeError("main_numbers must be a list or null")
            if any(
                isinstance(number, bool) or not isinstance(number, Integral) or number <= 0
                for number in main_numbers
            ):
                raise ValueError("main_numbers must contain positive integers")
            if len(main_numbers) != len(set(main_numbers)):
                raise ValueError("main_numbers cannot contain duplicate values")

    @staticmethod
    def analyze(
        draws: list[LotteryDraw], lottery_id: int | None = None
    ) -> dict[str, object]:
        StatisticalService._validate_draws(draws)

        if lottery_id is not None:
            draws = [draw for draw in draws if draw.lottery_id == lottery_id]

        ordered_draws = sorted(
            draws,
            key=lambda draw: (draw.draw_date, draw.id or 0),
        )
        frequency = collections.Counter(
            number
            for draw in ordered_draws
            for number in (draw.main_numbers or [])
        )
        parity = collections.Counter(
            f"{sum(number % 2 == 0 for number in (draw.main_numbers or []))}-"
            f"{sum(number % 2 != 0 for number in (draw.main_numbers or []))}"
            for draw in ordered_draws
            if draw.main_numbers
        )
        sums = [
            sum(draw.main_numbers or [])
            for draw in ordered_draws
            if draw.main_numbers
        ]

        pair_frequency = collections.Counter(
            pair
            for draw in ordered_draws
            for pair in itertools.combinations(sorted(set(draw.main_numbers or [])), 2)
        )

        consecutive_counts = []
        for draw in ordered_draws:
            numbers = sorted(set(draw.main_numbers or []))
            consecutive_counts.append(
                sum(
                    right == left + 1
                    for left, right in itertools.pairwise(numbers)
                )
            )

        recency: dict[int, dict[str, int]] = {}
        draw_count = len(ordered_draws)
        for index, draw in enumerate(ordered_draws, start=1):
            for number in set(draw.main_numbers or []):
                recency[number] = {
                    "last_seen_draw": index,
                    "draws_since_seen": draw_count - index,
                }

        return {
            "number_frequency": dict(sorted(frequency.items())),
            "number_recency": dict(sorted(recency.items())),
            "even_odd_distribution": dict(sorted(parity.items())),
            "sum_distribution": {
                "count": len(sums),
                "minimum": min(sums) if sums else None,
                "maximum": max(sums) if sums else None,
                "average": round(sum(sums) / len(sums), 2) if sums else None,
            },
            "pair_frequency": {
                f"{left}-{right}": count
                for (left, right), count in sorted(pair_frequency.items())
            },
            "consecutive_numbers": {
                "draws_with_consecutive": sum(count > 0 for count in consecutive_counts),
                "total_consecutive_pairs": sum(consecutive_counts),
                "maximum_consecutive_pairs": max(consecutive_counts)
                if consecutive_counts
                else 0,
            },
        }

    @staticmethod
    def overview(
        db: Session, lottery_id: int | None = None
    ) -> dict[str, int | str]:
        statement = select(LotteryDraw)
        if lottery_id is not None:
            statement = statement.where(LotteryDraw.lottery_id == lottery_id)

        draws = list(db.scalars(statement).all())
        if not draws:
            return {
                "module_status": "STANDBY",
                "algorithms_count": 0,
                "draws_analyzed": 0,
            }

        StatisticalService.analyze(draws, lottery_id=lottery_id)
        return {
            "module_status": "READY",
            "algorithms_count": len(STATISTICAL_ALGORITHMS),
            "draws_analyzed": len(draws),
        }
