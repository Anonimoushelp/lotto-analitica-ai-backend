from datetime import UTC, datetime

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.services.lottery_draw_service import LotteryDrawService


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def clear_database():
    db = SessionLocal()
    db.query(LotteryDraw).delete()
    db.query(Lottery).delete()
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def isolated_database():
    clear_database()
    yield
    clear_database()


def test_repository_create_rolls_back_after_database_failure(monkeypatch):
    db = SessionLocal()
    lottery = Lottery(code="ATOMIC-1", name="Atomic", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    draw = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="FAIL-1",
        draw_date=datetime(2026, 5, 1, tzinfo=UTC),
        main_numbers=[1, 2, 3, 4, 5],
    )

    def fail_commit():
        raise SQLAlchemyError("forced commit failure")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(SQLAlchemyError):
        LotteryDrawRepository.create(db=db, draw=draw)

    assert db.in_transaction() is False
    db.close()


def test_repository_delete_rolls_back_after_database_failure(monkeypatch):
    db = SessionLocal()
    lottery = Lottery(code="ATOMIC-2", name="Atomic", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    draw = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="DELETE-1",
        draw_date=datetime(2026, 5, 2, tzinfo=UTC),
        main_numbers=[1, 2, 3, 4, 5],
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    draw_id = draw.id

    original_commit = db.commit
    calls = 0

    def fail_delete_commit():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SQLAlchemyError("forced delete failure")
        original_commit()

    monkeypatch.setattr(db, "commit", fail_delete_commit)

    with pytest.raises(SQLAlchemyError):
        LotteryDrawRepository.delete(db=db, draw=draw)

    db.expire_all()
    assert db.get(LotteryDraw, draw_id) is not None
    db.close()


def test_update_integrity_error_rolls_back_without_partial_mutation(monkeypatch):
    db = SessionLocal()
    lottery = Lottery(code="ATOMIC-3", name="Atomic", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    first = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="UPDATE-1",
        draw_date=datetime(2026, 5, 3, tzinfo=UTC),
        main_numbers=[1, 2, 3, 4, 5],
    )
    second = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="UPDATE-2",
        draw_date=datetime(2026, 5, 4, tzinfo=UTC),
        main_numbers=[6, 7, 8, 9, 10],
    )
    db.add_all([first, second])
    db.commit()
    db.refresh(first)
    db.refresh(second)

    def fail_commit():
        raise IntegrityError("forced update conflict", {}, Exception())

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(HTTPException) as exc_info:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=first.id,
            update_data={"draw_number": "CONFLICTING-NUMBER"},
        )

    assert exc_info.value.status_code == 409
    db.expire_all()
    rows = db.scalars(
        select(LotteryDraw)
        .where(LotteryDraw.lottery_id == lottery.id)
        .order_by(LotteryDraw.id)
    ).all()
    assert [row.draw_number for row in rows] == ["UPDATE-1", "UPDATE-2"]
    assert [row.main_numbers for row in rows] == [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
    db.close()
