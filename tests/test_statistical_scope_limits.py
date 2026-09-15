from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.statistical_service import (
    StatisticalInputLimitError,
    StatisticalService,
)


def make_draw(numbers, draw_id, lottery_id, day_offset=0, draw_date=None):
    return SimpleNamespace(
        id=draw_id,
        draw_date=(
            date(2026, 1, 1) + timedelta(days=day_offset)
            if draw_date is None
            else draw_date
        ),
        lottery_id=lottery_id,
        main_numbers=numbers,
    )


def test_analyze_applies_lottery_scope_before_resource_limits():
    unrelated_draws = [
        make_draw([start, start + 1], index, lottery_id=2, day_offset=index)
        for index, start in enumerate(range(1, 10_003, 2), start=1)
    ]
    target_draw = make_draw([5, 12, 23, 31, 42], 20_000, lottery_id=1)

    result = StatisticalService.analyze(
        unrelated_draws + [target_draw], lottery_id=1
    )

    assert result["number_frequency"] == {
        5: 1,
        12: 1,
        23: 1,
        31: 1,
        42: 1,
    }


def test_analyze_ignores_invalid_draws_outside_selected_lottery_scope():
    unrelated_draw = make_draw(
        [1, 2, 3],
        1,
        lottery_id=2,
        draw_date=None,
    )
    target_draw = make_draw([5, 12, 23, 31, 42], 2, lottery_id=1)

    result = StatisticalService.analyze(
        [unrelated_draw, target_draw], lottery_id=1
    )

    assert result["sum_distribution"] == {
        "count": 1,
        "minimum": 113,
        "maximum": 113,
        "average": 113.0,
    }


def test_overview_accepts_exactly_maximum_analyzable_draws():
    draws = [
        make_draw([1, 2], index + 1, lottery_id=1, day_offset=index)
        for index in range(10_000)
    ]

    class FakeScalars:
        def all(self):
            return draws

    class FakeDb:
        def scalars(self, statement):
            return FakeScalars()

    result = StatisticalService.overview(FakeDb(), lottery_id=1)

    assert result["module_status"] == "READY"
    assert result["draws_analyzed"] == 10_000


def test_overview_fails_closed_when_database_read_is_truncated():
    draws = [
        make_draw([1, 2], index + 1, lottery_id=1, day_offset=index)
        for index in range(10_001)
    ]

    class FakeScalars:
        def all(self):
            return draws

    class FakeDb:
        def scalars(self, statement):
            return FakeScalars()

    with pytest.raises(StatisticalInputLimitError, match="input is too large"):
        StatisticalService.overview(FakeDb(), lottery_id=1)


def test_overview_query_is_hard_limited_to_one_over_service_maximum():
    captured = {}

    class FakeScalars:
        def all(self):
            return []

    class FakeDb:
        def scalars(self, statement):
            captured["limit"] = statement._limit_clause.value
            return FakeScalars()

    StatisticalService.overview(FakeDb(), lottery_id=1)

    assert captured["limit"] == 10_001


def test_validate_draws_accepts_exact_unique_number_cardinality_limit():
    draws = [
        make_draw(
            [number, number + 1],
            draw_id=number,
            lottery_id=1,
            day_offset=number,
        )
        for number in range(1, 10_001, 2)
    ]

    StatisticalService._validate_draws(draws)


def test_validate_draws_rejects_unique_pair_cardinality_before_unbounded_growth():
    draws = [
        make_draw(
            list(range(start, start + 100)),
            draw_id=start,
            lottery_id=1,
            day_offset=start,
        )
        for start in range(1, 2_101, 100)
    ]

    with pytest.raises(
        StatisticalInputLimitError,
        match="pair cardinality is too large",
    ):
        StatisticalService._validate_draws(draws)


def test_validate_draws_accepts_exact_pair_operation_limit():
    draw = make_draw(list(range(1, 101)), draw_id=1, lottery_id=1)
    draws = [draw for _ in range(202)]

    StatisticalService._validate_draws(draws)


def test_validate_draws_rejects_pair_operation_limit_plus_one():
    draw = make_draw(list(range(1, 101)), draw_id=1, lottery_id=1)
    draws = [draw for _ in range(203)]

    with pytest.raises(
        StatisticalInputLimitError,
        match="pair analysis input is too large",
    ):
        StatisticalService._validate_draws(draws)


def test_validate_draws_accepts_unique_pair_cardinality_below_limit():
    draws = [
        make_draw(
            list(range(start, start + 100)),
            draw_id=start,
            lottery_id=1,
            day_offset=start,
        )
        for start in range(1, 2_001, 100)
    ]

    StatisticalService._validate_draws(draws)
