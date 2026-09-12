from datetime import date
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def make_draw(draw_id, numbers, lottery_id=1):
    return SimpleNamespace(
        id=draw_id,
        lottery_id=lottery_id,
        draw_date=date(2026, 1, draw_id),
        main_numbers=numbers,
    )


def test_analyze_excludes_empty_draws_from_recency_and_consecutive_metrics():
    draws = [
        make_draw(1, [1, 2, 3]),
        make_draw(2, None),
        make_draw(3, []),
        make_draw(4, [3, 4]),
    ]

    result = StatisticalService.analyze(draws)

    assert result["number_frequency"] == {1: 1, 2: 1, 3: 2, 4: 1}
    assert result["sum_distribution"] == {
        "count": 2,
        "minimum": 6,
        "maximum": 7,
        "average": 6.5,
    }
    assert result["number_recency"][1] == {
        "last_seen_draw": 1,
        "draws_since_seen": 1,
    }
    assert result["number_recency"][3] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }
    assert result["consecutive_numbers"] == {
        "draws_with_consecutive": 1,
        "total_consecutive_pairs": 2,
        "maximum_consecutive_pairs": 2,
    }


def test_overview_stays_standby_when_all_draws_are_empty_or_null():
    class Db:
        def scalars(self, _statement):
            return self

        def all(self):
            return [make_draw(1, None), make_draw(2, [])]

    assert StatisticalService.overview(Db()) == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 0,
    }


def test_overview_counts_only_analyzable_draws():
    class Db:
        def scalars(self, _statement):
            return self

        def all(self):
            return [make_draw(1, None), make_draw(2, [5]), make_draw(3, [])]

    assert StatisticalService.overview(Db()) == {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 1,
    }


def test_analyze_empty_draws_is_same_as_filtering_them_before_analysis():
    draws = [make_draw(1, [2, 4]), make_draw(2, None), make_draw(3, [1, 3])]
    filtered = [draw for draw in draws if draw.main_numbers]

    assert StatisticalService.analyze(draws) == StatisticalService.analyze(filtered)
