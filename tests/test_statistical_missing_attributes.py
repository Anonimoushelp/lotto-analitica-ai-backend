from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def test_analyze_treats_missing_main_numbers_as_non_analyzable():
    missing_numbers = SimpleNamespace(
        id=1,
        draw_date=date(2026, 1, 1),
        lottery_id=1,
    )
    valid_draw = SimpleNamespace(
        id=2,
        draw_date=date(2026, 1, 2),
        lottery_id=1,
        main_numbers=[5, 12, 23, 31, 42],
    )

    result = StatisticalService.analyze([missing_numbers, valid_draw], lottery_id=1)

    assert result["sum_distribution"]["count"] == 1
    assert result["number_frequency"] == {5: 1, 12: 1, 23: 1, 31: 1, 42: 1}


def test_analyze_with_only_missing_main_numbers_returns_empty_analysis():
    missing_numbers = SimpleNamespace(
        id=1,
        draw_date=date(2026, 1, 1),
        lottery_id=1,
    )

    result = StatisticalService.analyze([missing_numbers], lottery_id=1)

    assert result["number_frequency"] == {}
    assert result["sum_distribution"]["count"] == 0
    assert result["consecutive_numbers"]["maximum_consecutive_pairs"] == 0
