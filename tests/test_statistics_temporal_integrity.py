from datetime import date

from app.models.lottery_draw import LotteryDraw
from app.services.statistical_service import StatisticalService


def _draw(draw_id: int, draw_date: date, numbers: list[int], lottery_id: int = 1) -> LotteryDraw:
    return LotteryDraw(
        id=draw_id,
        lottery_id=lottery_id,
        draw_date=draw_date,
        main_numbers=numbers,
    )


def test_analysis_orders_unsorted_draws_by_date_then_id() -> None:
    draws = [
        _draw(30, date(2026, 1, 3), [3, 6, 9]),
        _draw(10, date(2026, 1, 1), [1, 4, 7]),
        _draw(20, date(2026, 1, 2), [2, 5, 8]),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_recency"][3] == {"last_seen_draw": 3, "draws_since_seen": 0}
    assert result["number_recency"][1] == {"last_seen_draw": 1, "draws_since_seen": 2}


def test_same_date_uses_id_as_stable_tiebreaker_for_recency() -> None:
    draws = [
        _draw(20, date(2026, 1, 1), [2, 4, 6]),
        _draw(10, date(2026, 1, 1), [1, 3, 5]),
        _draw(30, date(2026, 1, 2), [2, 7, 8]),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_recency"][2] == {"last_seen_draw": 3, "draws_since_seen": 0}
    assert result["number_recency"][1] == {"last_seen_draw": 1, "draws_since_seen": 2}


def test_temporal_results_are_invariant_to_input_order() -> None:
    draws = [
        _draw(30, date(2026, 1, 3), [3, 6, 9]),
        _draw(10, date(2026, 1, 1), [1, 4, 7]),
        _draw(20, date(2026, 1, 2), [2, 5, 8]),
    ]

    forward = StatisticalService.analyze(draws)
    reverse = StatisticalService.analyze(list(reversed(draws)))

    assert forward == reverse


def test_recency_uses_draw_positions_not_calendar_day_gaps() -> None:
    draws = [
        _draw(1, date(2026, 1, 1), [1, 2, 3]),
        _draw(2, date(2026, 1, 15), [4, 5, 6]),
        _draw(3, date(2026, 3, 1), [1, 7, 8]),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_recency"][1] == {"last_seen_draw": 3, "draws_since_seen": 0}
    assert result["number_recency"][4] == {"last_seen_draw": 2, "draws_since_seen": 1}
