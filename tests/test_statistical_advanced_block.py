from datetime import date, timedelta
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, numbers, lottery_id=1, day_offset=0):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1) + timedelta(days=day_offset),
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


def test_all_algorithm_outputs_preserve_core_count_invariants():
    draws = [
        make_draw(1, [1, 2, 3, 7, 10]),
        make_draw(2, [2, 4, 6, 8, 10], day_offset=1),
        make_draw(3, [1, 4, 5, 8, 9], day_offset=2),
    ]

    result = StatisticalService.analyze(draws)
    draw_count = len(draws)
    number_count = sum(len(draw.main_numbers) for draw in draws)
    pair_count = sum(len(draw.main_numbers) * (len(draw.main_numbers) - 1) // 2 for draw in draws)

    assert sum(result["number_frequency"].values()) == number_count
    assert sum(result["even_odd_distribution"].values()) == draw_count
    assert result["sum_distribution"]["count"] == draw_count
    assert sum(result["pair_frequency"].values()) == pair_count


def test_consecutive_pairs_never_exceed_adjacent_bound_for_each_draw():
    draws = [
        make_draw(1, [1, 2, 3, 4, 5]),
        make_draw(2, [2, 4, 6, 8, 10], day_offset=1),
        make_draw(3, [10], day_offset=2),
    ]

    result = StatisticalService.analyze(draws)

    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 1,
        "total_consecutive_pairs": 4,
        "maximum_consecutive_pairs": 4,
    }


def test_recency_is_consistent_with_chronological_order_and_last_occurrence():
    draws = [
        make_draw(30, [9], day_offset=1),
        make_draw(10, [1, 9]),
        make_draw(20, [2, 9], day_offset=1),
        make_draw(40, [1], day_offset=2),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_recency"][9] == {
        "last_seen_draw": 3,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][1] == {
        "last_seen_draw": 4,
        "draws_since_seen": 0,
    }
    assert result["number_recency"][2] == {
        "last_seen_draw": 3,
        "draws_since_seen": 1,
    }


def test_analysis_does_not_mutate_input_draw_order_or_number_lists():
    draws = [
        make_draw(2, [5, 1, 3], day_offset=1),
        make_draw(1, [8, 2, 4]),
    ]
    original_order = list(draws)
    original_numbers = [list(draw.main_numbers) for draw in draws]

    StatisticalService.analyze(draws)

    assert draws == original_order
    assert [draw.main_numbers for draw in draws] == original_numbers


def test_lottery_filter_keeps_algorithm_counts_isolated():
    draws = [
        make_draw(1, [1, 2, 3], lottery_id=1),
        make_draw(2, [7, 8, 9], lottery_id=2, day_offset=1),
        make_draw(3, [1, 3, 5], lottery_id=1, day_offset=2),
    ]

    first = StatisticalService.analyze(draws, lottery_id=1)
    second = StatisticalService.analyze(draws, lottery_id=2)

    assert first["number_frequency"] == {1: 2, 2: 1, 3: 2, 5: 1}
    assert second["number_frequency"] == {7: 1, 8: 1, 9: 1}
    assert first["sum_distribution"]["count"] == 2
    assert second["sum_distribution"]["count"] == 1
    assert sum(first["pair_frequency"].values()) == 6
    assert sum(second["pair_frequency"].values()) == 3


def test_invalid_draw_collection_and_identifiers_fail_closed():
    valid_draws = [make_draw(1, [1, 2, 3])]

    try:
        StatisticalService.analyze(None)
    except TypeError as exc:
        assert "list of draws" in str(exc)
    else:
        raise AssertionError("Expected TypeError for a non-list draw collection")

    try:
        StatisticalService.analyze(valid_draws, lottery_id=True)
    except TypeError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("Expected TypeError for boolean lottery_id")

    try:
        StatisticalService.analyze(valid_draws, lottery_id=0)
    except ValueError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-positive lottery_id")
