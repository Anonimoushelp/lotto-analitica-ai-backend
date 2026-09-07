from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.tenant import Tenant
from app.repositories.lottery_repository import LotteryRepository
from app.services.lottery_draw_service import LotteryDrawService

pytestmark = pytest.mark.skipif(
    settings.environment != "test" or not settings.database_url.startswith("postgresql"),
    reason="requires PostgreSQL test environment",
)


def _seed_tenant(db, suffix: str) -> Tenant:
    tenant = Tenant(name=f"Tx {suffix}", slug=f"tx-{suffix}-{uuid4().hex[:8]}")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _seed_lottery(db, tenant_id: int, code: str) -> Lottery:
    lottery = Lottery(
        tenant_id=tenant_id,
        code=code,
        name=f"Lottery {code}",
        country="CO",
        active=True,
    )
    return LotteryRepository.create(db=db, lottery=lottery)


def _cleanup(db, tenant_ids: list[int]) -> None:
    db.query(LotteryDraw).filter(
        LotteryDraw.lottery_id.in_(
            select(Lottery.id).where(Lottery.tenant_id.in_(tenant_ids))
        )
    ).delete(synchronize_session=False)
    db.query(Lottery).filter(Lottery.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False
    )
    db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_lottery_repository_rollback_allows_same_session_to_continue():
    db = SessionLocal()
    tenant = _seed_tenant(db, "rollback")
    tenant_id = tenant.id
    code = f"RB-{uuid4().hex[:8]}"
    first = _seed_lottery(db, tenant_id, code)

    duplicate = Lottery(
        tenant_id=tenant_id,
        code=code,
        name="Duplicate",
        country="CO",
        active=True,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    second = _seed_lottery(db, tenant_id, f"OK-{uuid4().hex[:8]}")
    assert first.id != second.id
    assert db.scalar(select(Lottery).where(Lottery.id == second.id)) is not None

    _cleanup(db, [tenant_id])
    db.close()


def test_draw_service_failure_rolls_back_and_same_session_can_create_next_draw():
    db = SessionLocal()
    tenant = _seed_tenant(db, "draw-rollback")
    tenant_id = tenant.id
    lottery = _seed_lottery(db, tenant_id, f"DR-{uuid4().hex[:8]}")
    lottery_id = lottery.id
    first_date = datetime.now(UTC).replace(microsecond=0)
    second_date = first_date + timedelta(days=1)

    first = LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        lottery_id=lottery_id,
        draw_number=f"1-{uuid4().hex[:6]}",
        draw_date=first_date,
        main_numbers=[1, 2, 3, 4, 5],
    )
    second = LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        lottery_id=lottery_id,
        draw_number=f"2-{uuid4().hex[:6]}",
        draw_date=second_date,
        main_numbers=[6, 7, 8, 9, 10],
    )

    with pytest.raises(IntegrityError):
        LotteryDrawService.update_draw(
            db=db,
            draw_id=first.id,
            tenant_id=tenant_id,
            update_data={"draw_date": second_date},
        )

    db.rollback()
    persisted_first = db.scalar(
        select(LotteryDraw).where(LotteryDraw.id == first.id)
    )
    assert persisted_first is not None
    assert persisted_first.draw_date == first_date

    third = LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant_id,
        lottery_id=lottery_id,
        draw_number=f"3-{uuid4().hex[:6]}",
        draw_date=first_date + timedelta(days=2),
        main_numbers=[11, 12, 13, 14, 15],
    )
    assert third.id not in {first.id, second.id}

    _cleanup(db, [tenant_id])
    db.close()


def test_same_lottery_code_is_isolated_between_tenants():
    db = SessionLocal()
    tenant_a = _seed_tenant(db, "isolation-a")
    tenant_b = _seed_tenant(db, "isolation-b")
    tenant_a_id, tenant_b_id = tenant_a.id, tenant_b.id
    code = f"ISO-{uuid4().hex[:8]}"

    lottery_a = _seed_lottery(db, tenant_a_id, code)
    lottery_b = _seed_lottery(db, tenant_b_id, code)

    assert lottery_a.id != lottery_b.id
    assert LotteryRepository.get_by_code(db, code, tenant_a_id).id == lottery_a.id
    assert LotteryRepository.get_by_code(db, code, tenant_b_id).id == lottery_b.id
    assert LotteryRepository.get_by_id(db, lottery_a.id, tenant_b_id) is None
    assert LotteryRepository.get_by_id(db, lottery_b.id, tenant_a_id) is None

    _cleanup(db, [tenant_a_id, tenant_b_id])
    db.close()
