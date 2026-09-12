from contextlib import nullcontext
from datetime import date

from app.models.lottery_draw import LotteryDraw
from app.services.statistical_service import StatisticalService


class _ScalarResult:
    def __init__(self, draws):
        self._draws = draws

    def all(self):
        return self._draws


class _ReadOnlySession:
    def __init__(self, draws):
        self.draws = draws
        self.commit_calls = 0
        self.flush_calls = 0
        self.executed_statements = []
        self.autoflush_entered = 0

    @property
    def no_autoflush(self):
        self.autoflush_entered += 1
        return nullcontext()

    def scalars(self, statement):
        self.executed_statements.append(statement)
        return _ScalarResult(self.draws)

    def commit(self):
        self.commit_calls += 1
        raise AssertionError("Statistical overview must not commit")

    def flush(self):
        self.flush_calls += 1
        raise AssertionError("Statistical overview must not flush")


def _draw(draw_id: int, lottery_id: int, numbers: list[int]) -> LotteryDraw:
    return LotteryDraw(
        id=draw_id,
        lottery_id=lottery_id,
        draw_number=str(draw_id),
        draw_date=date(2026, 1, draw_id),
        main_numbers=numbers,
    )


def test_overview_is_read_only_and_does_not_mutate_session():
    db = _ReadOnlySession(
        [
            _draw(1, 10, [1, 2, 3, 4, 5]),
            _draw(2, 10, [2, 3, 4, 5, 6]),
        ]
    )

    result = StatisticalService.overview(db, lottery_id=10)

    assert result == {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 2,
    }
    assert db.commit_calls == 0
    assert db.flush_calls == 0
    assert db.autoflush_entered == 1
    assert len(db.executed_statements) == 1


def test_concurrent_read_calls_are_deterministic():
    draws = [
        _draw(1, 10, [1, 2, 3, 4, 5]),
        _draw(2, 10, [2, 4, 6, 8, 10]),
        _draw(3, 10, [1, 3, 5, 7, 9]),
    ]

    first = StatisticalService.analyze(draws, lottery_id=10)
    second = StatisticalService.analyze(list(reversed(draws)), lottery_id=10)

    assert first == second
