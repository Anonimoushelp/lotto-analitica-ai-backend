from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(numbers, draw_id, lottery_id=None, draw_date=date(2026, 1, 1)):
    return SimpleNamespace(
        id=draw_id,
        draw_date=draw_date,
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


def test_analyze_scope_uses_missing_lottery_id_as_nonmatching():
    target = make_draw([5, 12, 23, 31, 42], 1, lottery_id=1)
    malformed_unrelated = SimpleNamespace(
        id=2,
        draw_date=date(2026, 1, 1),
        main_numbers=[1, 2, 3],
    )

    result = StatisticalService.analyze(
        [malformed_unrelated, target], lottery_id=1
    )

    assert result["number_frequency"] == {
        5: 1,
        12: 1,
        23: 1,
        31: 1,
        42: 1,
    }


def test_analyze_without_scope_accepts_draw_with_null_lottery_id():
    draw = make_draw([5, 12, 23, 31, 42], 1, lottery_id=None)

    result = StatisticalService.analyze([draw])

    assert result["sum_distribution"]["count"] == 1
