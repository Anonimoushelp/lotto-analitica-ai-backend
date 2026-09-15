from datetime import date
from types import SimpleNamespace

import pytest

from app.services.statistical_service import StatisticalService


def test_analyze_rejects_non_integer_draw_id_before_ordering():
    malformed_draw = SimpleNamespace(
        id="not-an-integer",
        draw_date=date(2026, 1, 1),
        lottery_id=1,
        main_numbers=[5, 12, 23, 31, 42],
    )

    with pytest.raises(TypeError, match="draw id must be a positive integer or null"):
        StatisticalService.analyze([malformed_draw], lottery_id=1)


def test_analyze_rejects_non_positive_draw_id():
    malformed_draw = SimpleNamespace(
        id=0,
        draw_date=date(2026, 1, 1),
        lottery_id=1,
        main_numbers=[5, 12, 23, 31, 42],
    )

    with pytest.raises(ValueError, match="draw id must be a positive integer or null"):
        StatisticalService.analyze([malformed_draw], lottery_id=1)


def test_analyze_allows_missing_draw_id_for_duck_typed_input():
    draw_without_id = SimpleNamespace(
        draw_date=date(2026, 1, 1),
        lottery_id=1,
        main_numbers=[5, 12, 23, 31, 42],
    )

    result = StatisticalService.analyze([draw_without_id], lottery_id=1)

    assert result["sum_distribution"]["count"] == 1
    assert result["number_frequency"] == {5: 1, 12: 1, 23: 1, 31: 1, 42: 1}
