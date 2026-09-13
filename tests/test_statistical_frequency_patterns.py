from datetime import date, timedelta
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, numbers, day_offset, lottery_id=1):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 2, 1) + timedelta(days=day_offset),
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


def test_frequency_counts_every_valid_main_number_once_per_occurrence():
    draws = [
        make_draw(1, [1, 2, 3], 0),
        make_draw(2, [2, 3, 4], 1),
        make_draw(3, [2, 4, 5], 2),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_frequency"] == {
        1: 1,
        2: 3,
        3: 2,
        4: 2,
        5: 1,
    }


def test_frequency_is_independent_of_input_order():
    draws = [
        make_draw(3, [2, 4, 5], 2),
        make_draw(1, [1, 2, 3], 0),
        make_draw(2, [2, 3, 4], 1),
    ]

    forward = StatisticalService.analyze(draws)
    reverse = StatisticalService.analyze(list(reversed(draws)))

    assert forward["number_frequency"] == reverse["number_frequency"]
    assert forward["pair_frequency"] == reverse["pair_frequency"]
    assert forward["even_odd_distribution"] == reverse["even_odd_distribution"]
    assert forward["sum_distribution"] == reverse["sum_distribution"]
    assert forward["consecutive_numbers"] == reverse["consecutive_numbers"]
    assert forward["number_recency"] == reverse["number_recency"]


def test_frequency_and_derived_metrics_are_isolated_by_lottery():
    draws = [
        make_draw(1, [1, 2, 3], 0, lottery_id=10),
        make_draw(2, [2, 4, 6], 1, lottery_id=20),
        make_draw(3, [2, 3, 5], 2, lottery_id=10),
    ]

    result = StatisticalService.analyze(draws, lottery_id=10)

    assert result["number_frequency"] == {1: 1, 2: 2, 3: 2, 5: 1}
    assert result["sum_distribution"] == {
        "count": 2,
        "minimum": 6,
        "maximum": 10,
        "average": 8.0,
    }
    assert result["number_recency"][2] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }
    assert 6 not in result["number_frequency"]


def test_empty_and_non_analyzable_draws_return_empty_metrics():
    draws = [make_draw(1, None, 0), make_draw(2, None, 1)]

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
