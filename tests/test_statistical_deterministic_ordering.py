from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(numbers, *, draw_id=None, source="", draw_number=""):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1),
        lottery_id=1,
        main_numbers=numbers,
        source=source,
        draw_number=draw_number,
    )


def test_analyze_is_deterministic_for_same_date_and_id_with_different_input_order():
    first = make_draw([1, 2], draw_id=None, source="source-a", draw_number="A")
    second = make_draw([3, 4], draw_id=None, source="source-a", draw_number="B")

    result_forward = StatisticalService.analyze([first, second], lottery_id=1)
    result_reverse = StatisticalService.analyze([second, first], lottery_id=1)

    assert result_forward == result_reverse
    assert result_forward["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result_forward["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_uses_draw_number_to_break_same_date_and_id_source_ties():
    first = make_draw([1, 2], draw_id=7, source="provider")
    first.draw_number = "001"
    second = make_draw([3, 4], draw_id=7, source="provider")
    second.draw_number = "002"

    result = StatisticalService.analyze([second, first], lottery_id=1)

    assert result["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analyze_uses_main_numbers_as_final_deterministic_tie_breaker():
    first = make_draw([1, 4], draw_id=None)
    second = make_draw([2, 3], draw_id=None)

    result_forward = StatisticalService.analyze([first, second], lottery_id=1)
    result_reverse = StatisticalService.analyze([second, first], lottery_id=1)

    assert result_forward == result_reverse
