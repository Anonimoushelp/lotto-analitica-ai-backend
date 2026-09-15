from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.statistical_service import (
    StatisticalInputLimitError,
    StatisticalService,
)


def draw(numbers, draw_id, day_offset=0):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1) + timedelta(days=day_offset),
        lottery_id=1,
        main_numbers=numbers,
    )


def test_unique_number_cardinality_limit_prevents_unbounded_result_maps():
    draws = [
        draw(list(range(start, start + 100)), index, index)
        for index, start in enumerate(range(1, 10_102, 100), start=1)
    ]

    with pytest.raises(StatisticalInputLimitError, match="number cardinality is too large"):
        StatisticalService.analyze(draws)


def test_unique_pair_cardinality_limit_prevents_unbounded_pair_result_map():
    draws = [
        draw(list(range(start, start + 100)), index, index)
        for index, start in enumerate(range(1, 2_102, 100), start=1)
    ]

    with pytest.raises(StatisticalInputLimitError, match="pair cardinality is too large"):
        StatisticalService.analyze(draws)
