from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.draw_result import DrawResult
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)
DrawResult.__table__.create(bind=engine)


def db_session():
    return TestingSessionLocal()


def seed_lottery(db, name: str) -> Lottery:
    lottery = Lottery(
        name=name,
        code=name.lower().replace(" ", "-"),
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def draw_payload(lottery_id: int, draw_number: str = "D-001", draw_date=date(2026, 9, 2)):
    return {
        "lottery_id": lottery_id,
        "draw_number": draw_number,
        "draw_date": draw_date,
        "main_numbers": [1, 2, 3, 4, 5],
        "bonus_numbers": [6],
        "source": "test",
        "metadata_json": {"fixture": True},
    }


@pytest.fixture

def db():
    session = db_session()
    try:
        yield session
    finally:
        session.close()
        cleanup = db_session()
        cleanup.execute(delete(DrawResult))
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()


def test_create_draw_persists_valid_record(db):
    lottery = seed_lottery(db, "MiLoto")

    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    assert draw.id is not None
    assert draw.lottery_id == lottery.id
    assert draw.draw_number == "D-001"
    assert draw.main_numbers == [1, 2, 3, 4, 5]
    assert draw.bonus_numbers == [6]


def test_create_draw_rejects_missing_lottery(db):
    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(db=db, **draw_payload(999))

    assert exc.value.status_code == 404


def test_create_draw_rejects_duplicate_number_per_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db,
            **draw_payload(lottery.id, draw_date=date(2026, 9, 3)),
        )

    assert exc.value.status_code == 409
    assert "draw number" in exc.value.detail.lower()


def test_create_draw_allows_multiple_draws_on_same_date(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    second = LotteryDrawService.create_draw(
        db=db,
        **draw_payload(lottery.id, draw_number="D-002"),
    )

    assert first.id != second.id
    assert first.draw_date == second.draw_date


def test_same_number_and_date_are_allowed_for_different_lotteries(db):
    first = seed_lottery(db, "MiLoto")
    second = seed_lottery(db, "Baloto")

    first_draw = LotteryDrawService.create_draw(db=db, **draw_payload(first.id))
    second_draw = LotteryDrawService.create_draw(db=db, **draw_payload(second.id))

    assert first_draw.id != second_draw.id


def test_update_draw_persists_valid_changes(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    updated = LotteryDrawService.update_draw(
        db=db,
        draw_id=draw.id,
        update_data={
            "draw_number": "D-002",
            "draw_date": date(2026, 9, 3),
            "main_numbers": [10, 11, 12, 13, 14],
        },
    )

    assert updated.draw_number == "D-002"
    assert updated.draw_date == date(2026, 9, 3)
    assert updated.main_numbers == [10, 11, 12, 13, 14]


def test_update_draw_rejects_duplicate_number(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))
    second = LotteryDrawService.create_draw(
        db=db,
        **draw_payload(lottery.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=second.id,
            update_data={"draw_number": first.draw_number},
        )

    assert exc.value.status_code == 409


def test_update_draw_allows_same_date_for_distinct_draw_numbers(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))
    second = LotteryDrawService.create_draw(
        db=db,
        **draw_payload(lottery.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )

    updated = LotteryDrawService.update_draw(
        db=db,
        draw_id=second.id,
        update_data={"draw_date": first.draw_date},
    )

    assert updated.draw_date == first.draw_date


def test_update_draw_rejects_missing_target_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={"lottery_id": 999},
        )

    assert exc.value.status_code == 404


def test_delete_draw_removes_record(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    LotteryDrawService.delete_draw(db=db, draw_id=draw.id)

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.get_draw(db=db, draw_id=draw.id)

    assert exc.value.status_code == 404


def test_list_draws_filters_by_lottery_and_orders_by_date(db):
    first = seed_lottery(db, "MiLoto")
    second = seed_lottery(db, "Baloto")
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(first.id, draw_number="D-001", draw_date=date(2026, 9, 1)),
    )
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(first.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(second.id, draw_number="D-001", draw_date=date(2026, 9, 2)),
    )

    draws = LotteryDrawService.list_draws(db=db, lottery_id=first.id, limit=100)

    assert [item.draw_number for item in draws] == ["D-002", "D-001"]
    assert all(item.lottery_id == first.id for item in draws)

    
def test_create_draw_normalizes_multiple_result_groups(db):
    lottery = seed_lottery(db, "MultiModal")
    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="D-100",
        draw_date=date(2026, 9, 2),
        main_numbers=None,
        bonus_numbers=None,
        result_groups=[
            {"group_code": "main", "position": 1, "value": "12", "numeric_value": 12},
            {"group_code": "main", "position": 2, "value": "34", "numeric_value": 34},
            {"group_code": "bonus", "position": 1, "value": "X", "numeric_value": None},
        ],
    )

    assert [(item.group_code, item.position, item.value) for item in draw.results] == [
        ("bonus", 1, "X"),
        ("main", 1, "12"),
        ("main", 2, "34"),
    ]
