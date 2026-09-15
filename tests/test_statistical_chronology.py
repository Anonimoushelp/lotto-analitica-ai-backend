from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(numbers, *, draw_date, draw_id=None, source="", draw_number=""):
    return SimpleNamespace(
        id=draw_id,
        draw_date=draw_date,
        lottery_id=1,
        main_numbers=numbers,
        source=source,
        draw_number=draw_number,
    )


def test_analyze_orders_recency_by_draw_date_before_id():
    older = make_draw([1, 2], draw_date=date(2026, 1, 1), draw_id=99)
    newer = make_draw([3, 4], draw_date=date(2026, 1, 2), draw_id=1)

    result = StatisticalService.analyze([newer, older], lottery_id=1)

    assert result["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_orders_recency_by_id_when_dates_match():
    first = make_draw([1, 2], draw_date=date(2026, 1, 1), draw_id=10)
    second = make_draw([3, 4], draw_date=date(2026, 1, 1), draw_id=11)

    result = StatisticalService.analyze([second, first], lottery_id=1)

    assert result["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_uses_source_as_tie_breaker_when_date_and_id_match():
    first = make_draw(
        [1, 2], draw_date=date(2026, 1, 1), draw_id=10, source="provider-a"
    )
    second = make_draw(
        [3, 4], draw_date=date(2026, 1, 1), draw_id=10, source="provider-b"
    )

    result = StatisticalService.analyze([second, first], lottery_id=1)

    assert result["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }
