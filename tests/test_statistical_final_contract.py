from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def _draw(draw_id, draw_date, numbers, lottery_id=1):
    return SimpleNamespace(
        id=draw_id,
        lottery_id=lottery_id,
        draw_date=draw_date,
        main_numbers=numbers,
    )


def test_statistical_engine_exposes_complete_v1_contract():
    draws = [
        _draw(1, date(2026, 1, 1), [1, 2, 4]),
        _draw(2, date(2026, 1, 2), [2, 3, 4]),
    ]

    result = StatisticalService.analyze(draws, lottery_id=1)

    assert set(result) == {
        "number_frequency",
        "number_recency",
        "even_odd_distribution",
        "sum_distribution",
        "pair_frequency",
        "consecutive_numbers",
    }
    assert result["number_frequency"][2] == 2
    assert result["sum_distribution"]["count"] == 2
    assert result["pair_frequency"]["2-4"] == 2
    assert result["consecutive_numbers"]["draws_with_consecutive"] == 2


def test_statistical_engine_filters_lottery_without_cross_resource_leakage():
    draws = [
        _draw(1, date(2026, 1, 1), [1, 2], lottery_id=1),
        _draw(2, date(2026, 1, 2), [2, 3], lottery_id=2),
    ]

    result = StatisticalService.analyze(draws, lottery_id=1)

    assert result["number_frequency"] == {1: 1, 2: 1}
    assert result["sum_distribution"] == {
        "count": 1,
        "minimum": 3,
        "maximum": 3,
        "average": 3.0,
    }
    assert "2-3" not in result["pair_frequency"]


def test_statistical_engine_returns_stable_empty_contract():
    result = StatisticalService.analyze([])

    assert result == {
        "number_frequency": {},
        "number_recency": {},
        "even_odd_distribution": {},
        "sum_distribution": {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "average": None,
        },
        "pair_frequency": {},
        "consecutive_numbers": {
            "draws_with_consecutive": 0,
            "total_consecutive_pairs": 0,
            "maximum_consecutive_pairs": 0,
        },
    }
