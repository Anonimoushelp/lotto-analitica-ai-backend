from datetime import date
from types import SimpleNamespace

import pytest

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, lottery_id, draw_date, numbers):
    return SimpleNamespace(
        id=draw_id,
        lottery_id=lottery_id,
        draw_date=date.fromisoformat(draw_date),
        main_numbers=numbers,
    )


def test_all_statistical_outputs_share_the_same_analyzable_draw_population():
    draws = [
        make_draw(1, 10, "2026-01-01", [1, 2, 3]),
        make_draw(2, 10, "2026-01-02", None),
        make_draw(3, 10, "2026-01-03", [2, 4, 6]),
        make_draw(4, 20, "2026-01-04", [9, 10, 11]),
    ]

    result = StatisticalService.analyze(draws, lottery_id=10)

    assert sum(result["number_frequency"].values()) == 6
    assert result["sum_distribution"] == {
        "count": 2,
        "minimum": 6,
        "maximum": 12,
        "average": 9.0,
    }
    assert sum(result["even_odd_distribution"].values()) == 2
    assert sum(result["pair_frequency"].values()) == 6
    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 2,
        "total_consecutive_pairs": 2,
        "maximum_consecutive_pairs": 2,
    }
    assert result["number_recency"][2] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analysis_is_deterministic_for_input_order_and_uses_draw_id_as_tiebreaker():
    draws = [
        make_draw(2, 10, "2026-01-01", [1, 4]),
        make_draw(1, 10, "2026-01-01", [2, 3]),
        make_draw(3, 10, "2026-01-02", [4, 5]),
    ]

    forward = StatisticalService.analyze(draws, lottery_id=10)
    reverse = StatisticalService.analyze(list(reversed(draws)), lottery_id=10)

    assert forward == reverse
    assert forward["number_recency"][1] == {"last_seen_draw": 1, "draws_since_seen": 2}
    assert forward["number_recency"][4] == {"last_seen_draw": 3, "draws_since_seen": 0}


def test_empty_and_single_draw_results_have_explicit_numeric_contract():
    empty = StatisticalService.analyze([])
    single = StatisticalService.analyze(
        [make_draw(1, 10, "2026-01-01", [2, 5, 7])]
    )

    assert empty["number_frequency"] == {}
    assert empty["number_recency"] == {}
    assert empty["even_odd_distribution"] == {}
    assert empty["sum_distribution"] == {
        "count": 0,
        "minimum": None,
        "maximum": None,
        "average": None,
    }
    assert empty["pair_frequency"] == {}
    assert empty["consecutive_numbers"] == {
        "draws_with_consecutive": 0,
        "total_consecutive_pairs": 0,
        "maximum_consecutive_pairs": 0,
    }

    assert single["sum_distribution"] == {
        "count": 1,
        "minimum": 14,
        "maximum": 14,
        "average": 14.0,
    }
    assert single["consecutive_numbers"] == {
        "draws_with_consecutive": 1,
        "total_consecutive_pairs": 1,
        "maximum_consecutive_pairs": 1,
    }


def test_invalid_draw_numbers_and_lottery_ids_fail_closed():
    with pytest.raises(ValueError, match="positive integers"):
        StatisticalService.analyze(
            [make_draw(1, 10, "2026-01-01", [1, 1])]
        )

    with pytest.raises(TypeError, match="lottery_id"):
        StatisticalService.analyze([], lottery_id=True)

    with pytest.raises(ValueError, match="lottery_id"):
        StatisticalService.analyze([], lottery_id=0)
