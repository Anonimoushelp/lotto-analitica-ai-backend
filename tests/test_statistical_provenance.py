from datetime import date

from app.models.lottery_draw import LotteryDraw
from app.schemas.statistics import StatisticalOverviewResponse
from app.services.statistical_service import StatisticalService


class _ScalarResult:
    def __init__(self, draws):
        self._draws = draws

    def all(self):
        return self._draws


class _DB:
    class _NoAutoflush:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    no_autoflush = _NoAutoflush()

    def __init__(self, draws):
        self.draws = draws

    def scalars(self, statement):
        return _ScalarResult(self.draws)


def _draw(source: str, draw_id: int) -> LotteryDraw:
    return LotteryDraw(
        id=draw_id,
        lottery_id=1,
        draw_number=f"2026-{draw_id:03d}",
        draw_date=date(2026, 9, draw_id),
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=[6],
        source=source,
    )


def test_overview_exposes_exact_sources_of_analyzed_draws():
    db = _DB([_draw("baloto-colombia", 1), _draw("revancha-colombia", 2)])

    result = StatisticalService.overview(db)

    assert result["module_status"] == "READY"
    assert result["draws_analyzed"] == 2
    assert result["sources"] == ["baloto-colombia", "revancha-colombia"]


def test_scoped_overview_exposes_only_requested_source():
    db = _DB([_draw("baloto-colombia", 1), _draw("revancha-colombia", 2)])

    result = StatisticalService.overview(db, source="baloto-colombia")

    assert result["sources"] == ["baloto-colombia"]


def test_standby_overview_has_empty_source_provenance():
    db = _DB([LotteryDraw(
        id=1,
        lottery_id=1,
        draw_number="2026-001",
        draw_date=date(2026, 9, 1),
        main_numbers=[],
        bonus_numbers=None,
        source="baloto-colombia",
    )])

    result = StatisticalService.overview(db)

    assert result == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 0,
        "sources": [],
    }


def test_statistical_overview_response_requires_sources():
    response = StatisticalOverviewResponse(
        module_status="READY",
        algorithms_count=6,
        draws_analyzed=2,
        sources=["baloto-colombia"],
    )

    assert response.sources == ["baloto-colombia"]
