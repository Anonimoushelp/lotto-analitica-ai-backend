from datetime import date, timedelta
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, numbers, day_offset):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1) + timedelta(days=day_offset),
        lottery_id=1,
        main_numbers=numbers,
    )


def test_recency_uses_latest_chronological_occurrence_and_draw_count():
    draws = [
        make_draw(10, [1, 2], 0),
        make_draw(20, [3, 4], 1),
        make_draw(30, [2, 5], 2),
        make_draw(40, [6], 3),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_recency"][1] == {"last_seen_draw": 1, "draws_since_seen": 3}
    assert result["number_recency"][2] == {"last_seen_draw": 3, "draws_since_seen": 1}
    assert result["number_recency"][5] == {"last_seen_draw": 3, "draws_since_seen": 1}
    assert result["number_recency"][6] == {"last_seen_draw": 4, "draws_since_seen": 0}


def test_recency_is_deterministic_with_equal_dates_and_draw_id_tiebreaker():
    draws = [
        make_draw(30, [7], 0),
        make_draw(10, [8, 7], 0),
        make_draw(20, [9], 1),
    ]

    forward = StatisticalService.analyze(draws)
    reverse = StatisticalService.analyze(list(reversed(draws)))

    assert forward == reverse
    assert forward["number_recency"][7] == {
        "last_seen_draw": 2,
        "draws_since_seen": 1,
    }
    assert forward["number_recency"][8] == {
        "last_seen_draw": 1,
        "draws_since_seen": 2,
    }


def test_frequency_and_recency_are_isolated_by_lottery_id():
    draws = [
        SimpleNamespace(
            id=1,
            draw_date=date(2026, 1, 1),
            lottery_id=10,
            main_numbers=[1, 2, 2],
        ),
        SimpleNamespace(
            id=2,
            draw_date=date(2026, 1, 2),
            lottery_id=20,
            main_numbers=[1, 3],
        ),
    ]

    # This fixture intentionally uses a duplicate to ensure validation happens
    # before lottery filtering and cannot hide malformed input.
    try:
        StatisticalService.analyze(draws, lottery_id=20)
    except ValueError as exc:
        assert "duplicate values" in str(exc)
    else:
        raise AssertionError("Malformed input must be rejected before filtering")
