from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
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
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    yield session
    session.close()
    cleanup = TestingSessionLocal()
    cleanup.query(LotteryDraw).delete()
    cleanup.query(Lottery).delete()
    cleanup.commit()
    cleanup.close()


def seed_lottery(db, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def seed_draw(db, lottery_id: int, source: str, number: str, day: int) -> LotteryDraw:
    draw = LotteryDraw(
        lottery_id=lottery_id,
        draw_number=number,
        draw_date=date(2026, 9, day),
        main_numbers=[1, 2, 3, 4, 5],
        source=source,
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    return draw


def test_update_conflict_rolls_back_all_changed_fields(db):
    lottery = seed_lottery(db, "TX-UPDATE-1")
    first = seed_draw(db, lottery.id, "baloto-colombia", "D-001", 18)
    second = seed_draw(db, lottery.id, "baloto-colombia", "D-002", 19)

    with pytest.raises(Exception) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=first.id,
            update_data={
                "draw_number": second.draw_number,
                "draw_date": second.draw_date,
                "main_numbers": [10, 11, 12],
            },
        )

    assert getattr(exc.value, "status_code", None) == 409
    db.expire_all()
    persisted = db.get(LotteryDraw, first.id)
    assert persisted.draw_number == "D-001"
    assert persisted.draw_date == date(2026, 9, 18)
    assert persisted.main_numbers == [1, 2, 3, 4, 5]


def test_update_integrity_error_rolls_back_database_transaction(db, monkeypatch):
    lottery = seed_lottery(db, "TX-UPDATE-2")
    draw = seed_draw(db, lottery.id, "baloto-colombia", "D-001", 18)
    original_commit = db.commit
    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise IntegrityError("UPDATE lottery_draws", {}, Exception("simulated race"))
        original_commit()

    monkeypatch.setattr(db, "commit", fail_once)

    with pytest.raises(Exception) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={"main_numbers": [20, 21, 22]},
        )

    assert getattr(exc.value, "status_code", None) == 409
    db.expire_all()
    persisted = db.get(LotteryDraw, draw.id)
    assert persisted.main_numbers == [1, 2, 3, 4, 5]


def test_update_conflict_is_isolated_by_source_and_lottery(db):
    lottery_a = seed_lottery(db, "TX-UPDATE-3A")
    lottery_b = seed_lottery(db, "TX-UPDATE-3B")
    source_a = seed_draw(db, lottery_a.id, "baloto-colombia", "D-001", 18)
    source_b = seed_draw(db, lottery_a.id, "revancha-colombia", "D-001", 18)
    other_lottery = seed_draw(db, lottery_b.id, "baloto-colombia", "D-001", 18)

    updated = LotteryDrawService.update_draw(
        db=db,
        draw_id=source_a.id,
        update_data={"lottery_id": lottery_b.id, "draw_number": "D-002", "draw_date": date(2026, 9, 19)},
    )

    assert updated.lottery_id == lottery_b.id
    assert updated.draw_number == "D-002"
    assert db.get(LotteryDraw, source_b.id).draw_number == "D-001"
    assert db.get(LotteryDraw, other_lottery.id).draw_number == "D-001"


def test_for_update_repository_method_emits_row_lock():
    class ScalarSession:
        def __init__(self):
            self.statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

    db = ScalarSession()
    assert LotteryDrawRepository.get_by_id_for_update(db, 42) is None
    assert db.statement is not None
    assert "FOR UPDATE" in str(db.statement.compile(compile_kwargs={"literal_binds": True}))


def test_update_missing_draw_does_not_start_mutation_transaction(db):
    with pytest.raises(Exception) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=999999,
            update_data={"main_numbers": [20, 21, 22]},
        )

    assert getattr(exc.value, "status_code", None) == 404
    assert db.scalars(select(LotteryDraw)).all() == []
