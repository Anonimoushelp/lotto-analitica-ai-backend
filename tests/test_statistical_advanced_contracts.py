from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, numbers, lottery_id=1, day_offset=0):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1) + timedelta(days=day_offset),
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


def test_sum_distribution_uses_all_analyzable_draws_and_rounds_average():
    draws = [
        make_draw(1, [1, 2]),
        make_draw(2, [1, 2, 3], day_offset=1),
        make_draw(3, [10], day_offset=2),
    ]

    result = StatisticalService.analyze(draws)

    assert result["sum_distribution"] == {
        "count": 3,
        "minimum": 3,
        "maximum": 10,
        "average": 6.33,
    }


def test_pair_frequency_counts_each_unordered_pair_once_per_draw():
    draws = [
        make_draw(1, [3, 1, 2]),
        make_draw(2, [2, 3, 4], day_offset=1),
    ]

    result = StatisticalService.analyze(draws)

    assert result["pair_frequency"] == {
        "1-2": 1,
        "1-3": 1,
        "2-3": 2,
        "2-4": 1,
        "3-4": 1,
    }


def test_consecutive_algorithm_counts_only_adjacent_values():
    draws = [
        make_draw(1, [1, 2, 4, 5, 7]),
        make_draw(2, [2, 4, 6], day_offset=1),
        make_draw(3, [8, 9, 10], day_offset=2),
    ]

    result = StatisticalService.analyze(draws)

    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 2,
        "total_consecutive_pairs": 4,
        "maximum_consecutive_pairs": 2,
    }


def test_number_frequency_and_parity_are_integer_valued_and_deterministically_sorted():
    draws = [
        make_draw(2, [4, 1, 3]),
        make_draw(1, [2, 4, 1], day_offset=1),
    ]

    result = StatisticalService.analyze(draws)

    assert list(result["number_frequency"]) == [1, 2, 3, 4]
    assert all(isinstance(value, int) for value in result["number_frequency"].values())
    assert list(result["even_odd_distribution"]) == ["1-2", "2-1"]
    assert all(isinstance(value, int) for value in result["even_odd_distribution"].values())


def test_empty_analyzable_dataset_returns_null_sum_bounds_and_zero_consecutive_metrics():
    draws = [make_draw(1, None)]

    result = StatisticalService.analyze(draws)

    assert result["number_frequency"] == {}
    assert result["number_recency"] == {}
    assert result["even_odd_distribution"] == {}
    assert result["sum_distribution"] == {
        "count": 0,
        "minimum": None,
        "maximum": None,
        "average": None,
    }
    assert result["pair_frequency"] == {}
    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 0,
        "total_consecutive_pairs": 0,
        "maximum_consecutive_pairs": 0,
    }


def test_datetime_draw_date_is_rejected_by_the_statistical_contract():
    draw = make_draw(1, [1, 2])
    draw.draw_date = datetime(2026, 1, 1, 12, 30)

    with pytest.raises(TypeError, match="valid draw_date"):
        StatisticalService.analyze([draw])
