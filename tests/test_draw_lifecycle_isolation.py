from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_repository import LotteryRepository
from app.services.lottery_draw_service import LotteryDrawService
from app.services.lottery_service import LotteryService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def db_session():
    return TestingSessionLocal()


@pytest.fixture
def db():
    session = db_session()
    try:
        yield session
    finally:
        session.close()
        cleanup = db_session()
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()


def seed_lottery(db, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def seed_draw(db, lottery_id: int, source: str, draw_number: str = "D-001") -> LotteryDraw:
    draw = LotteryDraw(
        lottery_id=lottery_id,
        draw_number=draw_number,
        draw_date=date(2026, 9, 18),
        main_numbers=[1, 2, 3, 4, 5],
        source=source,
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    return draw


def test_delete_draw_preserves_same_draw_number_from_other_provider(db):
    lottery = seed_lottery(db, "shared-provider-lottery")
    baloto = seed_draw(db, lottery.id, "baloto-colombia")
    revancha = seed_draw(db, lottery.id, "revancha-colombia")

    LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)

    assert db.get(LotteryDraw, baloto.id) is None
    survivor = db.get(LotteryDraw, revancha.id)
    assert survivor is not None
    assert survivor.source == "revancha-colombia"
    assert survivor.draw_number == "D-001"


def test_delete_lottery_cascades_only_its_draws_and_preserves_other_lottery(db):
    first = seed_lottery(db, "lottery-a")
    second = seed_lottery(db, "lottery-b")
    first_draw = seed_draw(db, first.id, "baloto-colombia")
    second_draw = seed_draw(db, second.id, "revancha-colombia")

    LotteryService.delete_lottery(db=db, lottery_id=first.id)

    assert db.get(Lottery, first.id) is None
    assert db.get(LotteryDraw, first_draw.id) is None
    surviving_lottery = db.get(Lottery, second.id)
    surviving_draw = db.get(LotteryDraw, second_draw.id)
    assert surviving_lottery is not None
    assert surviving_draw is not None
    assert surviving_draw.lottery_id == second.id
    assert surviving_draw.source == "revancha-colombia"


def test_delete_lottery_removes_all_provider_draws_for_that_lottery(db):
    lottery = seed_lottery(db, "multi-provider-lottery")
    baloto = seed_draw(db, lottery.id, "baloto-colombia")
    revancha = seed_draw(db, lottery.id, "revancha-colombia")

    LotteryService.delete_lottery(db=db, lottery_id=lottery.id)

    assert db.get(Lottery, lottery.id) is None
    assert db.get(LotteryDraw, baloto.id) is None
    assert db.get(LotteryDraw, revancha.id) is None


def test_delete_lottery_not_found_does_not_mutate_data(db):
    lottery = seed_lottery(db, "not-found-lottery")
    draw = seed_draw(db, lottery.id, "miloto-colombia")

    with pytest.raises(HTTPException) as exc:
        LotteryService.delete_lottery(db=db, lottery_id=999999)

    assert exc.value.status_code == 404
    assert db.get(Lottery, lottery.id) is not None
    assert db.get(LotteryDraw, draw.id) is not None


def test_delete_lottery_integrity_error_rolls_back_without_orphans(db, monkeypatch):
    lottery = seed_lottery(db, "rollback-lottery")
    draw = seed_draw(db, lottery.id, "baloto-colombia")
    integrity_error = IntegrityError(
        "DELETE FROM lotteries",
        {},
        Exception("foreign key constraint"),
    )

    def raise_integrity(**kwargs):
        raise integrity_error

    monkeypatch.setattr(LotteryRepository, "delete", raise_integrity)

    with pytest.raises(IntegrityError):
        LotteryService.delete_lottery(db=db, lottery_id=lottery.id)

    db.rollback()
    assert db.get(Lottery, lottery.id) is not None
    assert db.get(LotteryDraw, draw.id) is not None
