import collections
import itertools
from contextlib import nullcontext
from datetime import date, datetime
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

_MAX_ANALYZABLE_DRAWS = 10_000
_MAX_NUMBERS_PER_DRAW = 100
_MAX_PAIR_OPERATIONS = 1_000_000
_MAX_UNIQUE_NUMBERS = 10_000
_MAX_UNIQUE_PAIRS = 100_000


class StatisticalInputLimitError(ValueError):
    """Raised when statistical input exceeds safe computational bounds."""


class StatisticalService:
    @staticmethod
    def _validate_draws(draws: list[LotteryDraw]) -> None:
        if not isinstance(draws, list):
            raise TypeError("Statistical analysis requires a list of draws")
        if len(draws) > _MAX_ANALYZABLE_DRAWS:
            raise StatisticalInputLimitError("Statistical analysis input is too large")

        pair_operations = 0
        unique_numbers: set[int] = set()
        unique_pairs: set[tuple[int, int]] = set()
        for draw in draws:
            draw_date = getattr(draw, "draw_date", None)
            if isinstance(draw_date, datetime) or not isinstance(draw_date, date):
                raise TypeError("Each draw must have a valid draw_date")

            main_numbers = getattr(draw, "main_numbers", None)
            if main_numbers is None:
                continue
            if not isinstance(main_numbers, list):
                raise TypeError("main_numbers must be a list or null")
            if len(main_numbers) > _MAX_NUMBERS_PER_DRAW:
                raise StatisticalInputLimitError("A draw contains too many numbers")
            if any(
                isinstance(number, bool) or not isinstance(number, Integral) or number <= 0
                for number in main_numbers
            ):
                raise ValueError("main_numbers must contain positive integers")
            if len(main_numbers) != len(set(main_numbers)):
                raise ValueError("main_numbers cannot contain duplicate values")

            unique_numbers.update(main_numbers)
            if len(unique_numbers) > _MAX_UNIQUE_NUMBERS:
                raise StatisticalInputLimitError("Statistical number cardinality is too large")

            normalized_numbers = sorted(main_numbers)
            unique_pairs.update(itertools.combinations(normalized_numbers, 2))
            if len(unique_pairs) > _MAX_UNIQUE_PAIRS:
                raise StatisticalInputLimitError("Statistical pair cardinality is too large")

            pair_operations += len(main_numbers) * (len(main_numbers) - 1) // 2
            if pair_operations > _MAX_PAIR_OPERATIONS:
                raise StatisticalInputLimitError("Statistical pair analysis input is too large")

    @staticmethod
    def _validate_lottery_id(lottery_id: int | None) -> None:
        if lottery_id is None:
            return
        if isinstance(lottery_id, bool) or not isinstance(lottery_id, Integral):
            raise TypeError("lottery_id must be a positive integer or null")
        if lottery_id <= 0:
            raise ValueError("lottery_id must be a positive integer or null")

    @staticmethod
    def analyze(
        draws: list[LotteryDraw], lottery_id: int | None = None
    ) -> dict[str, object]:
        if not isinstance(draws, list):
            raise TypeError("Statistical analysis requires a list of draws")
        StatisticalService._validate_lottery_id(lottery_id)

        if lottery_id is not None:
            draws = [draw for draw in draws if draw.lottery_id == lottery_id]

        StatisticalService._validate_draws(draws)

        ordered_draws = sorted(
            (draw for draw in draws if draw.main_numbers),
            key=lambda draw: (draw.draw_date, draw.id or 0),
        )
        frequency = collections.Counter(
            number
            for draw in ordered_draws
            for number in draw.main_numbers
        )
        parity = collections.Counter(
            f"{sum(number % 2 == 0 for number in draw.main_numbers)}-"
            f"{sum(number % 2 != 0 for number in draw.main_numbers)}"
            for draw in ordered_draws
        )
        sums = [sum(draw.main_numbers) for draw in ordered_draws]

        pair_frequency = collections.Counter(
            pair
            for draw in ordered_draws
            for pair in itertools.combinations(sorted(set(draw.main_numbers)), 2)
        )

        consecutive_counts = []
        for draw in ordered_draws:
            numbers = sorted(set(draw.main_numbers))
            consecutive_counts.append(
                sum(
                    right == left + 1
                    for left, right in itertools.pairwise(numbers)
                )
            )

        recency: dict[int, dict[str, int]] = {}
        draw_count = len(ordered_draws)
        for index, draw in enumerate(ordered_draws, start=1):
            for number in set(draw.main_numbers):
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
        StatisticalService._validate_lottery_id(lottery_id)
        statement = select(LotteryDraw)
        if lottery_id is not None:
            statement = statement.where(LotteryDraw.lottery_id == lottery_id)
        statement = statement.limit(_MAX_ANALYZABLE_DRAWS + 1)

        autoflush_context = getattr(db, "no_autoflush", nullcontext())
        with autoflush_context:
            draws = list(db.scalars(statement).all())
        if len(draws) > _MAX_ANALYZABLE_DRAWS:
            raise StatisticalInputLimitError("Statistical analysis input is too large")

        analyzable_draws = [draw for draw in draws if draw.main_numbers]
        if not analyzable_draws:
            return {
                "module_status": "STANDBY",
                "algorithms_count": 0,
                "draws_analyzed": 0,
            }

        StatisticalService.analyze(analyzable_draws, lottery_id=lottery_id)
        return {
            "module_status": "READY",
            "algorithms_count": len(STATISTICAL_ALGORITHMS),
            "draws_analyzed": len(analyzable_draws),
        }
