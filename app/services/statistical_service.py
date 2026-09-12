import itertools
from collections import Counter  # noqa: I001

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
    def analyze(draws: list[LotteryDraw]) -> dict[str, object]:
        ordered_draws = sorted(
            draws,
            key=lambda draw: (draw.draw_date, draw.id or 0),
        )
        frequency = Counter(
            number
            for draw in ordered_draws
            for number in (draw.main_numbers or [])
        )
        parity = Counter(
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

        pair_frequency = Counter(
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
