from datetime import date

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.statistical_service import StatisticalService

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    session.execute(delete(LotteryDraw))
    session.execute(delete(Lottery))
    session.commit()
    yield session
    session.execute(delete(LotteryDraw))
    session.execute(delete(Lottery))
    session.commit()
    session.close()


def seed_lottery(db: Session, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def test_failed_update_then_cross_provider_recovery_is_atomic(monkeypatch, db):
    lottery_a = seed_lottery(db, "PH374-A")
    lottery_b = seed_lottery(db, "PH374-B")
    baloto = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery_a.id,
        draw_number="37401",
        draw_date=date(2026, 9, 1),
        main_numbers=[1, 2, 3, 4, 5],
        source="baloto-colombia",
    )
    revancha = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery_b.id,
        draw_number="37401",
        draw_date=date(2026, 9, 1),
        main_numbers=[11, 12, 13, 14, 15],
        source="revancha-colombia",
    )

    original_commit = Session.commit
    state = {"failed": False}

    def fail_once(session):
        if not state["failed"]:
            state["failed"] = True
            raise IntegrityError("forced", {}, Exception("forced"))
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_once)

    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=baloto.id,
            update_data={
                "lottery_id": lottery_b.id,
                "draw_number": "37402",
                "draw_date": date(2026, 9, 2),
                "main_numbers": [21, 22, 23, 24, 25],
            },
        )
    assert getattr(exc_info.value, "status_code", None) == 409

    db.expire_all()
    persisted = db.get(LotteryDraw, baloto.id)
    assert persisted is not None
    assert persisted.lottery_id == lottery_a.id
    assert persisted.draw_number == "37401"
    assert persisted.draw_date == date(2026, 9, 1)
    assert persisted.main_numbers == [1, 2, 3, 4, 5]
    assert persisted.source == "baloto-colombia"

    recovered = LotteryDrawService.update_draw(
        db=db,
        draw_id=baloto.id,
        update_data={
            "draw_number": "37402",
            "draw_date": date(2026, 9, 2),
            "main_numbers": [21, 22, 23, 24, 25],
        },
    )
    assert recovered.id == baloto.id

    revancha_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_b.id, source="revancha-colombia", limit=100
    )
    baloto_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_a.id, source="baloto-colombia", limit=100
    )
    assert [row.id for row in revancha_rows] == [revancha.id]
    assert [row.id for row in baloto_rows] == [baloto.id]
    assert StatisticalService.analyze(
        revancha_rows, lottery_id=lottery_b.id, source="revancha-colombia"
    )["number_frequency"] == {11: 1, 12: 1, 13: 1, 14: 1, 15: 1}
    assert StatisticalService.analyze(
        baloto_rows, lottery_id=lottery_a.id, source="baloto-colombia"
    )["number_frequency"] == {21: 1, 22: 1, 23: 1, 24: 1, 25: 1}


def test_failed_delete_recovery_does_not_restore_other_scope_statistics(monkeypatch, db):
    lottery_a = seed_lottery(db, "PH374-C")
    lottery_b = seed_lottery(db, "PH374-D")
    baloto = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery_a.id,
        draw_number="37410",
        draw_date=date(2026, 9, 10),
        main_numbers=[31, 32, 33, 34, 35],
        source="baloto-colombia",
    )
    revancha = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery_b.id,
        draw_number="37410",
        draw_date=date(2026, 9, 10),
        main_numbers=[41, 42, 43, 44, 45],
        source="revancha-colombia",
    )

    original_commit = Session.commit

    def fail_once(session):
        monkeypatch.setattr(Session, "commit", original_commit)
        raise IntegrityError("forced", {}, Exception("forced"))

    monkeypatch.setattr(Session, "commit", fail_once)

    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
    assert getattr(exc_info.value, "status_code", None) == 409

    db.expire_all()
    assert db.get(LotteryDraw, baloto.id) is not None
    assert db.get(LotteryDraw, revancha.id) is not None

    LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)

    baloto_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_a.id, source="baloto-colombia", limit=100
    )
    revancha_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_b.id, source="revancha-colombia", limit=100
    )
    assert baloto_rows == []
    assert [row.id for row in revancha_rows] == [revancha.id]
    assert StatisticalService.overview(
        db, lottery_id=lottery_a.id, source="baloto-colombia"
    )["draws_analyzed"] == 0
    assert StatisticalService.overview(
        db, lottery_id=lottery_b.id, source="revancha-colombia"
    )["draws_analyzed"] == 1
    assert StatisticalService.analyze(
        revancha_rows, lottery_id=lottery_b.id, source="revancha-colombia"
    )["number_frequency"] == {41: 1, 42: 1, 43: 1, 44: 1, 45: 1}
