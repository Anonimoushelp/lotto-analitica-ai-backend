import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository


class FailingSession:
    def __init__(self):
        self.rollback_calls = 0
        self.commit_calls = 0
        self.refresh_calls = 0
        self.added = None
        self.deleted = None

    def add(self, value):
        self.added = value

    def delete(self, value):
        self.deleted = value

    def commit(self):
        self.commit_calls += 1
        raise SQLAlchemyError("database write failed")

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, value):
        self.refresh_calls += 1


def test_create_rolls_back_after_database_write_failure():
    db = FailingSession()
    draw = LotteryDraw(
        lottery_id=1,
        draw_number="900",
        draw_date="2026-09-13",
        main_numbers=[1, 2, 3, 4, 5],
    )

    with pytest.raises(SQLAlchemyError, match="database write failed"):
        LotteryDrawRepository.create(db=db, draw=draw)

    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert db.refresh_calls == 0
    assert db.added is draw


def test_delete_rolls_back_after_database_write_failure():
    db = FailingSession()
    draw = LotteryDraw(
        id=1,
        lottery_id=1,
        draw_number="901",
        draw_date="2026-09-13",
        main_numbers=[6, 7, 8, 9, 10],
    )

    with pytest.raises(SQLAlchemyError, match="database write failed"):
        LotteryDrawRepository.delete(db=db, draw=draw)

    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert db.deleted is draw


def test_draw_schema_keeps_provider_scoped_unique_identity_constraints():
    constraints = {
        constraint.name for constraint in LotteryDraw.__table__.constraints
    }

    assert "uq_lottery_draw_source_number" in constraints
    assert "uq_lottery_draw_source_date" in constraints


def test_draw_schema_keeps_cascade_delete_foreign_key():
    foreign_keys = list(LotteryDraw.__table__.c.lottery_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "CASCADE"
