from datetime import date
from types import SimpleNamespace

import pytest

from app.services.statistical_service import StatisticalService


def draw(draw_id, draw_date, numbers, lottery_id=1):
    return SimpleNamespace(
        id=draw_id,
        draw_date=draw_date,
        main_numbers=numbers,
        lottery_id=lottery_id,
    )


def test_frequency_pair_parity_sum_and_consecutive_invariants():
    draws = [
        draw(1, date(2026, 1, 1), [1, 2, 3, 7, 8]),
        draw(2, date(2026, 1, 2), [1, 3, 4, 8, 9]),
    ]

    result = StatisticalService.analyze(draws)

    assert sum(result["number_frequency"].values()) == 10
    assert sum(result["even_odd_distribution"].values()) == 2
    assert result["sum_distribution"] == {
        "count": 2,
        "minimum": 21,
        "maximum": 25,
        "average": 23.0,
    }
    assert result["pair_frequency"]["1-3"] == 2
    assert result["pair_frequency"]["1-2"] == 1
    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 2,
        "total_consecutive_pairs": 5,
        "maximum_consecutive_pairs": 3,
    }


def test_recency_is_based_on_chronological_draw_order():
    draws = [
        draw(30, date(2026, 3, 1), [5, 9]),
        draw(10, date(2026, 1, 1), [5, 7]),
        draw(20, date(2026, 2, 1), [7, 9]),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_recency"] == {
        5: {"last_seen_draw": 3, "draws_since_seen": 0},
        7: {"last_seen_draw": 2, "draws_since_seen": 1},
        9: {"last_seen_draw": 3, "draws_since_seen": 0},
    }


def test_same_date_draws_are_deterministic_by_id():
    draws = [
        draw(2, date(2026, 1, 1), [2]),
        draw(1, date(2026, 1, 1), [1]),
    ]

    forward = StatisticalService.analyze(draws)
    reverse = StatisticalService.analyze(list(reversed(draws)))

    assert forward == reverse
    assert forward["number_recency"][1] == {"last_seen_draw": 1, "draws_since_seen": 1}
    assert forward["number_recency"][2] == {"last_seen_draw": 2, "draws_since_seen": 0}


@pytest.mark.parametrize(
    "lottery_id",
    [0, -1, True, False, "1", 1.5],
)
def test_invalid_lottery_scope_is_rejected(lottery_id):
    draws = [draw(1, date(2026, 1, 1), [1, 2, 3])]

    with pytest.raises((TypeError, ValueError)):
        StatisticalService.analyze(draws, lottery_id=lottery_id)


def test_invalid_draw_shape_is_rejected_before_analysis():
    invalid_draws = [
        draw(1, date(2026, 1, 1), [1, True, 3]),
        draw(2, date(2026, 1, 2), [1, 1, 2]),
        draw(3, date(2026, 1, 3), [1, "2", 3]),
    ]

    for invalid in invalid_draws:
        with pytest.raises((TypeError, ValueError)):
            StatisticalService.analyze([invalid])


def test_null_main_numbers_are_ignored_but_invalid_dates_are_not():
    assert StatisticalService.analyze(
        [draw(1, date(2026, 1, 1), None)]
    )["sum_distribution"] == {
        "count": 0,
        "minimum": None,
        "maximum": None,
        "average": None,
    }

    with pytest.raises(TypeError):
        StatisticalService.analyze([draw(1, "2026-01-01", [1, 2])])


def test_lottery_scope_does_not_mutate_the_input_collection():
    draws = [
        draw(1, date(2026, 1, 1), [1, 2], lottery_id=1),
        draw(2, date(2026, 1, 2), [9, 10], lottery_id=2),
    ]
    original = list(draws)

    StatisticalService.analyze(draws, lottery_id=1)

    assert draws == original
    assert len(draws) == 2
