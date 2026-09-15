from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(numbers, *, draw_number):
    return SimpleNamespace(
        id=None,
        draw_date=date(2026, 1, 1),
        lottery_id=1,
        main_numbers=numbers,
        source="provider",
        draw_number=draw_number,
    )


def test_analyze_orders_numeric_draw_numbers_naturally_when_ids_are_missing():
    draw_2 = make_draw([2], draw_number="2")
    draw_10 = make_draw([10], draw_number="10")

    result = StatisticalService.analyze([draw_10, draw_2], lottery_id=1)

    assert result["number_recency"][2] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][10] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_keeps_numeric_draw_number_order_deterministic_for_zero_padding():
    first = make_draw([1], draw_number="001")
    second = make_draw([2], draw_number="1")

    forward = StatisticalService.analyze([first, second], lottery_id=1)
    reverse = StatisticalService.analyze([second, first], lottery_id=1)

    assert forward == reverse
    assert forward["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert forward["number_recency"][2] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_handles_extremely_long_numeric_draw_number_without_integer_conversion():
    draw_2 = make_draw([2], draw_number="2")
    huge_number = make_draw([3], draw_number="9" * 5000)

    result = StatisticalService.analyze([huge_number, draw_2], lottery_id=1)

    assert result["number_recency"][2] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }
