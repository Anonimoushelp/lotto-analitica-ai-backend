from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.plan import Plan
from app.models.tenant import Tenant
from app.repositories.lottery_repository import LotteryRepository
from app.services.lottery_service import LotteryService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Plan.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)


@pytest.fixture(autouse=True)
def clean_test_data():
    yield
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(Tenant))
    db.execute(delete(Plan))
    db.commit()
    db.close()


def new_tenant(db) -> Tenant:
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


def new_lottery(code: str, tenant_id: int) -> Lottery:
    now = datetime.now(UTC)
    return Lottery(
        tenant_id=tenant_id,
        code=code,
        name=f"Lottery {code}",
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )


def test_lottery_repository_rolls_back_failed_unique_insert():
    db = TestingSessionLocal()
    try:
        tenant = new_tenant(db)
        db.add(new_lottery("ROLLBACK-1", tenant.id))
        db.commit()

        duplicate = new_lottery("ROLLBACK-1", tenant.id)
        with pytest.raises(IntegrityError):
            LotteryRepository.create(db=db, lottery=duplicate)

        db.add(new_lottery("ROLLBACK-2", tenant.id))
        db.commit()
        assert db.query(Lottery).count() == 2
    finally:
        db.close()


def test_lottery_service_rejects_duplicate_code():
    db = TestingSessionLocal()
    try:
        tenant = new_tenant(db)
        db.add(new_lottery("DUP-1", tenant.id))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            LotteryService.create_lottery(
                db=db,
                payload={
                    "code": "DUP-1",
                    "name": "Duplicate",
                    "country": "CO",
                    "active": True,
                },
                tenant_id=tenant.id,
            )

        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_lottery_service_rejects_update_to_existing_code():
    db = TestingSessionLocal()
    try:
        tenant = new_tenant(db)
        first = new_lottery("UPD-1", tenant.id)
        second = new_lottery("UPD-2", tenant.id)
        db.add_all([first, second])
        db.commit()
        db.refresh(second)

        with pytest.raises(HTTPException) as exc_info:
            LotteryService.update_lottery(
                db=db,
                lottery_id=second.id,
                update_data={"code": "UPD-1"},
                tenant_id=tenant.id,
            )

        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_lottery_service_returns_404_for_missing_lottery():
    db = TestingSessionLocal()
    try:
        tenant = new_tenant(db)
        with pytest.raises(HTTPException) as exc_info:
            LotteryService.get_lottery(
                db=db,
                lottery_id=99999,
                tenant_id=tenant.id,
            )
        assert exc_info.value.status_code == 404
    finally:
        db.close()
