import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository


def test_repository_create_recovers_after_rollback():
    class RecoveringSession:
        def __init__(self):
            self.commit_attempts = 0
            self.rollback_called = False
            self.refreshed = None

        def add(self, value):
            self.pending = value

        def commit(self):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise SQLAlchemyError("transient database failure")

        def rollback(self):
            self.rollback_called = True

        def refresh(self, value):
            self.refreshed = value

    db = RecoveringSession()
    failed_draw = LotteryDraw(lottery_id=1, draw_number="RECOVERY-RETRY-001")
    recovered_draw = LotteryDraw(lottery_id=1, draw_number="RECOVERY-RETRY-002")

    with pytest.raises(SQLAlchemyError):
        LotteryDrawRepository.create(db, failed_draw)

    assert db.rollback_called is True

    result = LotteryDrawRepository.create(db, recovered_draw)

    assert result is recovered_draw
    assert db.commit_attempts == 2
    assert db.refreshed is recovered_draw


def test_health_returns_503_when_postgresql_is_unavailable(monkeypatch):
    from app.main import health

    class FailingSession:
        def execute(self, statement):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr("app.main.logger.exception", lambda *args, **kwargs: None)

    response = health(FailingSession())

    assert response.status_code == 503
    assert response.body == b'{"status":"unhealthy","service":"Lotto Analitica AI"}'
