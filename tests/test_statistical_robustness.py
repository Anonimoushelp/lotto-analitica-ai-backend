from datetime import date
from types import SimpleNamespace

import pytest

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, numbers, lottery_id=1):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1),
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


def test_single_number_and_pair_draws_have_zero_or_one_pair_without_errors():
    result = StatisticalService.analyze([make_draw(1, [7]), make_draw(2, [2, 5])])
    assert result["pair_frequency"] == {"2-5": 1}
    assert result["consecutive_numbers"] == {"draws_with_consecutive": 0, "total_consecutive_pairs": 0, "maximum_consecutive_pairs": 0}


def test_large_valid_number_values_remain_exact_in_frequency_and_pairs():
    result = StatisticalService.analyze([make_draw(1, [1_000_000, 2_000_000, 2_000_001])])
    assert result["number_frequency"] == {1_000_000: 1, 2_000_000: 1, 2_000_001: 1}
    assert result["pair_frequency"] == {"1000000-2000000": 1, "1000000-2000001": 1, "2000000-2000001": 1}
    assert result["consecutive_numbers"]["total_consecutive_pairs"] == 1


@pytest.mark.parametrize("numbers", [[0, 1], [-1, 2], [1.0, 2], [True, 2], [1, 2, 2]])
def test_invalid_number_domains_are_rejected_before_analysis(numbers):
    with pytest.raises((TypeError, ValueError)):
        StatisticalService.analyze([make_draw(1, numbers)])


def test_none_main_numbers_are_excluded_without_affecting_valid_metrics():
    result = StatisticalService.analyze([make_draw(1, None), make_draw(2, [3, 4]), make_draw(3, None)])
    assert result["sum_distribution"] == {"count": 1, "minimum": 7, "maximum": 7, "average": 7.0}
    assert result["number_frequency"] == {3: 1, 4: 1}
    assert result["number_recency"] == {3: {"last_seen_draw": 1, "draws_since_seen": 0}, 4: {"last_seen_draw": 1, "draws_since_seen": 0}}
