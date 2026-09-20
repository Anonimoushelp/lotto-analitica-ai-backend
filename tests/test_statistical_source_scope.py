from datetime import date

from app.models.lottery_draw import LotteryDraw
from app.services.statistical_service import StatisticalService


def _draw(draw_id: int, lottery_id: int, source: str, numbers: list[int]) -> LotteryDraw:
    return LotteryDraw(
        id=draw_id,
        lottery_id=lottery_id,
        source=source,
        draw_number=str(draw_id),
        draw_date=date(2026, 1, draw_id),
        main_numbers=numbers,
    )


def test_analysis_source_scope_excludes_other_providers():
    draws = [
        _draw(1, 10, "baloto-colombia", [1, 2, 3]),
        _draw(2, 10, "miloto-colombia", [9, 10, 11]),
        _draw(3, 10, "baloto-colombia", [1, 4, 7]),
    ]

    result = StatisticalService.analyze(
        draws,
        lottery_id=10,
        source="baloto-colombia",
    )

    assert result["number_frequency"] == {1: 2, 2: 1, 3: 1, 4: 1, 7: 1}
    assert 9 not in result["number_frequency"]
    assert 10 not in result["number_frequency"]


def test_analysis_source_is_normalized_without_cross_provider_contamination():
    draws = [
        _draw(1, 10, "baloto-colombia", [1, 2, 3]),
        _draw(2, 10, "miloto-colombia", [9, 10, 11]),
    ]

    result = StatisticalService.analyze(
        draws,
        lottery_id=10,
        source="  baloto-colombia  ",
    )

    assert result["number_frequency"] == {1: 1, 2: 1, 3: 1}
