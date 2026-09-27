import collections
import itertools
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
    def _validate_lottery_id(lottery_id: int | None) -> None:
        if lottery_id is not None and (
            isinstance(lottery_id, bool) or not isinstance(lottery_id, Integral) or lottery_id <= 0
        ):
            raise ValueError("lottery_id must be a positive integer or null")

    @staticmethod
    def _validate_draws(draws: list[LotteryDraw]) -> None:
        if len(draws) > _MAX_ANALYZABLE_DRAWS:
            raise StatisticalInputLimitError("Statistical analysis input is too large")
        unique_numbers: set[int] = set()
        unique_pairs: set[tuple[int, int]] = set()
        pair_operations = 0
        for draw in draws:
            draw_date = getattr(draw, "draw_date", None)
            if isinstance(draw_date, datetime) or not isinstance(draw_date, date):
                raise TypeError("Each draw must have a valid draw_date")
            numbers = getattr(draw, "main_numbers", None) or []
            if not isinstance(numbers, list):
                raise TypeError("main_numbers must be a list or null")
            if len(numbers) > _MAX_NUMBERS_PER_DRAW:
                raise StatisticalInputLimitError("A draw contains too many numbers")
            if any(isinstance(n, bool) or not isinstance(n, Integral) or n <= 0 for n in numbers):
                raise ValueError("main_numbers must contain positive integers")
            if len(numbers) != len(set(numbers)):
                raise ValueError("main_numbers cannot contain duplicate values")
            unique_numbers.update(numbers)
            if len(unique_numbers) > _MAX_UNIQUE_NUMBERS:
                raise StatisticalInputLimitError("Statistical number cardinality is too large")
            pair_operations += len(numbers) * (len(numbers) - 1) // 2
            if pair_operations > _MAX_PAIR_OPERATIONS:
                raise StatisticalInputLimitError("Statistical pair analysis input is too large")
            unique_pairs.update(itertools.combinations(sorted(numbers), 2))
            if len(unique_pairs) > _MAX_UNIQUE_PAIRS:
                raise StatisticalInputLimitError("Statistical pair cardinality is too large")

    @staticmethod
    def _draw_key(draw: LotteryDraw):
        return (
            draw.draw_date,
            getattr(draw, "id", 0) or 0,
            str(getattr(draw, "source", "") or ""),
            str(getattr(draw, "draw_number", "") or ""),
        )

    @staticmethod
    def analyze(draws: list[LotteryDraw], lottery_id: int | None = None, source: str | None = None) -> dict[str, object]:
        StatisticalService._validate_lottery_id(lottery_id)
        normalized_source = source.strip() if source is not None else None
        if source is not None and (not normalized_source or len(normalized_source) > 255):
            raise ValueError("source must be a non-empty string or null")
        scoped = [d for d in draws if
                  (lottery_id is None or getattr(d, "lottery_id", None) == lottery_id) and
                  (normalized_source is None or getattr(d, "source", None) == normalized_source)]
        StatisticalService._validate_draws(scoped)
        ordered = sorted((d for d in scoped if getattr(d, "main_numbers", None)), key=StatisticalService._draw_key)
        frequency = collections.Counter(n for d in ordered for n in d.main_numbers)
        parity = collections.Counter(
            f"{sum(n % 2 == 0 for n in d.main_numbers)}-{sum(n % 2 != 0 for n in d.main_numbers)}" for d in ordered
        )
        sums = [sum(d.main_numbers) for d in ordered]
        pairs = collections.Counter(pair for d in ordered for pair in itertools.combinations(sorted(set(d.main_numbers)), 2))
        consecutive = [sum(r == l + 1 for l, r in itertools.pairwise(sorted(set(d.main_numbers)))) for d in ordered]
        recency = {}
        for index, draw in enumerate(ordered, start=1):
            for number in set(draw.main_numbers):
                recency[number] = {"last_seen_draw": index, "draws_since_seen": len(ordered) - index}
        return {
            "number_frequency": dict(sorted(frequency.items())),
            "number_recency": dict(sorted(recency.items())),
            "even_odd_distribution": dict(sorted(parity.items())),
            "sum_distribution": {"count": len(sums), "minimum": min(sums) if sums else None, "maximum": max(sums) if sums else None, "average": round(sum(sums) / len(sums), 2) if sums else None},
            "pair_frequency": {f"{a}-{b}": count for (a, b), count in sorted(pairs.items())},
            "consecutive_numbers": {"draws_with_consecutive": sum(c > 0 for c in consecutive), "total_consecutive_pairs": sum(consecutive), "maximum_consecutive_pairs": max(consecutive) if consecutive else 0},
        }

    @staticmethod
    def overview(db: Session, lottery_id: int | None = None, source: str | None = None):
        StatisticalService._validate_lottery_id(lottery_id)
        statement = select(LotteryDraw)
        if lottery_id is not None:
            statement = statement.where(LotteryDraw.lottery_id == lottery_id)
        if source is not None:
            source = source.strip()
            if not source:
                raise ValueError("source must be a non-empty string or null")
            statement = statement.where(LotteryDraw.source == source)
        draws = list(db.scalars(statement.limit(_MAX_ANALYZABLE_DRAWS + 1)).all())
        if len(draws) > _MAX_ANALYZABLE_DRAWS:
            raise StatisticalInputLimitError("Statistical analysis input is too large")
        analyzable = [d for d in draws if getattr(d, "main_numbers", None)]
        if not analyzable:
            return {"module_status": "STANDBY", "algorithms_count": 0, "draws_analyzed": 0}
        StatisticalService.analyze(analyzable, lottery_id=lottery_id, source=source)
        return {"module_status": "READY", "algorithms_count": len(STATISTICAL_ALGORITHMS), "draws_analyzed": len(analyzable)}
