from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.plan import Plan
from app.models.tenant import Tenant
from app.services.lottery_draw_service import LotteryDrawService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Plan.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def db_session():
    return TestingSessionLocal()


def seed_tenant(db) -> Tenant:
    plan = db.scalar(select(Plan).where(Plan.code == "free"))
    if plan is None:
        plan = Plan(code="free", name="Free", is_active=True)
        db.add(plan)
        db.flush()
    tenant = Tenant(name="Test Tenant", slug="test-tenant", plan_id=plan.id)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def seed_lottery(db, name: str) -> Lottery:
    tenant = db.query(Tenant).first() or seed_tenant(db)
    lottery = Lottery(
        name=name,
        code=name.lower().replace(" ", "-"),
        country="Colombia",
        tenant_id=tenant.id,
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def draw_payload(
    lottery_id: int,
    draw_number: str = "D-001",
    draw_date=date(2026, 9, 2),
):
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
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.execute(delete(Tenant))
        cleanup.execute(delete(Plan))
        cleanup.commit()
        cleanup.close()


def test_create_draw_persists_valid_record(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(
        db=db, tenant_id=lottery.tenant_id, **draw_payload(lottery.id)
    )

    assert draw.id is not None
    assert draw.lottery_id == lottery.id
    assert draw.draw_number == "D-001"
    assert draw.main_numbers == [1, 2, 3, 4, 5]
    assert draw.bonus_numbers == [6]


def test_create_draw_rejects_missing_lottery(db):
    tenant = seed_tenant(db)
    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db, tenant_id=tenant.id, **draw_payload(999)
        )
    assert exc.value.status_code == 404


def test_create_draw_rejects_duplicate_number_per_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    tenant_id = lottery.tenant_id
    LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db,
            tenant_id=tenant_id,
            **draw_payload(lottery.id, draw_date=date(2026, 9, 3)),
        )

    assert exc.value.status_code == 409
    assert "draw number" in exc.value.detail.lower()


def test_create_draw_rejects_duplicate_date_per_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    tenant_id = lottery.tenant_id
    LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db,
            tenant_id=tenant_id,
            **draw_payload(lottery.id, draw_number="D-002"),
        )

    assert exc.value.status_code == 409
    assert "draw date" in exc.value.detail.lower()


def test_same_number_and_date_are_allowed_for_different_lotteries(db):
    first = seed_lottery(db, "MiLoto")
    second = seed_lottery(db, "Baloto")
    tenant_id = first.tenant_id

    first_draw = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(first.id)
    )
    second_draw = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(second.id)
    )

    assert first_draw.id != second_draw.id


def test_update_draw_persists_valid_changes(db):
    lottery = seed_lottery(db, "MiLoto")
    tenant_id = lottery.tenant_id
    draw = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )

    updated = LotteryDrawService.update_draw(
        db=db,
        draw_id=draw.id,
        tenant_id=tenant_id,
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
    tenant_id = lottery.tenant_id
    first = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )
    second = LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        **draw_payload(lottery.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=second.id,
            tenant_id=tenant_id,
            update_data={"draw_number": first.draw_number},
        )

    assert exc.value.status_code == 409


def test_update_draw_rejects_duplicate_date(db):
    lottery = seed_lottery(db, "MiLoto")
    tenant_id = lottery.tenant_id
    first = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )
    second = LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        **draw_payload(lottery.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=second.id,
            tenant_id=tenant_id,
            update_data={"draw_date": first.draw_date},
        )

    assert exc.value.status_code == 409


def test_update_draw_rejects_missing_target_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    tenant_id = lottery.tenant_id
    draw = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            tenant_id=tenant_id,
            update_data={"lottery_id": 999},
        )

    assert exc.value.status_code == 404


def test_delete_draw_removes_record(db):
    lottery = seed_lottery(db, "MiLoto")
    tenant_id = lottery.tenant_id
    draw = LotteryDrawService.create_draw(
        db=db, tenant_id=tenant_id, **draw_payload(lottery.id)
    )

    LotteryDrawService.delete_draw(db=db, draw_id=draw.id, tenant_id=tenant_id)

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.get_draw(db=db, draw_id=draw.id, tenant_id=tenant_id)

    assert exc.value.status_code == 404


def test_list_draws_filters_by_lottery_and_orders_by_date(db):
    first = seed_lottery(db, "MiLoto")
    second = seed_lottery(db, "Baloto")
    tenant_id = first.tenant_id
    LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        **draw_payload(first.id, draw_number="D-001", draw_date=date(2026, 9, 1)),
    )
    LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        **draw_payload(first.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )
    LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        **draw_payload(second.id, draw_number="D-001", draw_date=date(2026, 9, 2)),
    )

    draws = LotteryDrawService.list_draws(
        db=db, tenant_id=tenant_id, lottery_id=first.id, limit=100
    )

    assert [item.draw_number for item in draws] == ["D-002", "D-001"]
    assert all(item.lottery_id == first.id for item in draws)
