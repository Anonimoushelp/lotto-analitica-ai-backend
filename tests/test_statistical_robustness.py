from datetime import date
from types import SimpleNamespace

import pytest

from app.services.statistical_service import StatisticalService


def draw(numbers, draw_id=1, draw_date=date(2026, 1, 1), lottery_id=1):
    return SimpleNamespace(
        id=draw_id,
        draw_date=draw_date,
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


@pytest.mark.parametrize(
    "numbers",
    [
        [1, 2, 2, 4],
        [1, "2", 3],
        [1, 2.5, 3],
        [1, True, 3],
        [1, 0, 3],
        [1, -2, 3],
        "1,2,3",
        {1, 2, 3},
    ],
)
def test_analyze_rejects_corrupt_main_numbers(numbers):
    with pytest.raises(ValueError):
        StatisticalService.analyze([draw(numbers)])


def test_analyze_rejects_missing_or_invalid_draw_date():
    with pytest.raises(ValueError):
        StatisticalService.analyze([draw([1, 2], draw_date=None)])

    with pytest.raises(ValueError):
        StatisticalService.analyze([draw([1, 2], draw_date="2026-01-01")])


def test_analyze_accepts_null_main_numbers_without_fabricating_data():
    result = StatisticalService.analyze([draw(None)])
    assert result["number_frequency"] == {}
    assert result["number_recency"] == {}
    assert result["even_odd_distribution"] == {}
    assert result["sum_distribution"]["count"] == 0
    assert result["pair_frequency"] == {}
    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 0,
        "total_consecutive_pairs": 0,
        "maximum_consecutive_pairs": 0,
    }


def test_analyze_accepts_empty_and_variable_size_draws():
    result = StatisticalService.analyze(
        [
            draw([], draw_id=1),
            draw([7], draw_id=2, draw_date=date(2026, 1, 2)),
            draw([1, 2, 3], draw_id=3, draw_date=date(2026, 1, 3)),
            draw([4, 8, 15, 16, 23, 42], draw_id=4, draw_date=date(2026, 1, 4)),
        ]
    )
    assert result["number_frequency"] == {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        7: 1,
        8: 1,
        15: 1,
        16: 1,
        23: 1,
        42: 1,
    }
    assert result["sum_distribution"] == {
        "count": 3,
        "minimum": 7,
        "maximum": 108,
        "average": 44.0,
    }


def test_analyze_requires_list_input():
    with pytest.raises(ValueError):
        StatisticalService.analyze(tuple([draw([1, 2])]))


def test_analyze_is_deterministic_with_same_date_using_id_tiebreaker():
    first = draw([1, 2], draw_id=1)
    second = draw([2, 3], draw_id=2)
    first.draw_date = second.draw_date = date(2026, 1, 1)

    expected = StatisticalService.analyze([first, second])
    assert expected == StatisticalService.analyze([second, first])
    assert expected["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert expected["number_recency"][2] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_scope_filters_before_calculation():
    result = StatisticalService.analyze(
        [
            draw([1, 2, 3], draw_id=1, lottery_id=10),
            draw([40, 41, 42], draw_id=2, lottery_id=20, draw_date=date(2026, 1, 2)),
        ],
        lottery_id=10,
    )
    assert result["number_frequency"] == {1: 1, 2: 1, 3: 1}
    assert 40 not in result["number_frequency"]
