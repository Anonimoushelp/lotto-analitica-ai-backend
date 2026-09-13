from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw

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


def test_unique_draw_number_is_enforced_per_lottery_transactionally():
    db = SessionLocal()
    lottery = Lottery(code="TX-1", name="Transactional", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    draw_a = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="DUP-1",
        draw_date=datetime(2026, 2, 1, tzinfo=UTC),
        main_numbers=[1, 2, 3, 4, 5],
    )
    draw_b = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="DUP-1",
        draw_date=datetime(2026, 2, 2, tzinfo=UTC),
        main_numbers=[6, 7, 8, 9, 10],
    )
    db.add(draw_a)
    db.commit()
    db.add(draw_b)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()
    assert db.scalar(select(LotteryDraw).where(LotteryDraw.draw_number == "DUP-1")).id == draw_a.id
    db.close()


def test_unique_draw_date_is_enforced_per_lottery_transactionally():
    db = SessionLocal()
    lottery = Lottery(code="TX-2", name="Transactional", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    draw_date = datetime(2026, 3, 1, tzinfo=UTC)
    first = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="DATE-1",
        draw_date=draw_date,
        main_numbers=[1, 2, 3, 4, 5],
    )
    second = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="DATE-2",
        draw_date=draw_date,
        main_numbers=[6, 7, 8, 9, 10],
    )
    db.add(first)
    db.commit()
    db.add(second)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()
    rows = db.scalars(select(LotteryDraw).where(LotteryDraw.lottery_id == lottery.id)).all()
    assert len(rows) == 1
    assert rows[0].draw_number == "DATE-1"
    db.close()


def test_failed_transaction_can_recover_and_persist_followup_mutation():
    db = SessionLocal()
    lottery = Lottery(code="TX-3", name="Transactional", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    existing = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="RECOVER-1",
        draw_date=datetime(2026, 4, 1, tzinfo=UTC),
        main_numbers=[1, 2, 3, 4, 5],
    )
    db.add(existing)
    db.commit()

    duplicate = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="RECOVER-1",
        draw_date=datetime(2026, 4, 2, tzinfo=UTC),
        main_numbers=[6, 7, 8, 9, 10],
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    recovered = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="RECOVER-2",
        draw_date=datetime(2026, 4, 2, tzinfo=UTC),
        main_numbers=[6, 7, 8, 9, 10],
    )
    db.add(recovered)
    db.commit()

    rows = db.scalars(
        select(LotteryDraw)
        .where(LotteryDraw.lottery_id == lottery.id)
        .order_by(LotteryDraw.id)
    ).all()
    assert [row.draw_number for row in rows] == ["RECOVER-1", "RECOVER-2"]
    db.close()
