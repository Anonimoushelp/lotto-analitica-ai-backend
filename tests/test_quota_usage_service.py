import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.user import User
from app.services.quota_usage_service import (
    QuotaUsageNotSupportedError,
    QuotaUsageService,
)


def test_quota_usage_is_tenant_scoped() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        plan = Plan(code="free", name="Free", is_active=True)
        db.add(plan)
        db.flush()

        tenant_a = Tenant(name="Tenant A", slug="tenant-a", plan_id=plan.id)
        tenant_b = Tenant(name="Tenant B", slug="tenant-b", plan_id=plan.id)
        user_a = User(email="a@example.com", hashed_password="x", is_active=True)
        user_b = User(email="b@example.com", hashed_password="x", is_active=True)
        db.add_all([tenant_a, tenant_b, user_a, user_b])
        db.flush()

        db.add_all(
            [
                Membership(tenant_id=tenant_a.id, user_id=user_a.id, role="admin"),
                Membership(tenant_id=tenant_b.id, user_id=user_b.id, role="admin"),
                Membership(tenant_id=tenant_a.id, user_id=user_b.id, role="viewer", is_active=False),
                Lottery(
                    tenant_id=tenant_a.id,
                    code="A",
                    name="Lottery A",
                    country="CO",
                    active=True,
                ),
                Lottery(
                    tenant_id=tenant_a.id,
                    code="A-INACTIVE",
                    name="Lottery A inactive",
                    country="CO",
                    active=False,
                ),
                Lottery(
                    tenant_id=tenant_b.id,
                    code="B",
                    name="Lottery B",
                    country="CO",
                    active=True,
                ),
            ]
        )
        db.flush()

        lottery_a = db.scalar(
            select(Lottery).where(Lottery.tenant_id == tenant_a.id, Lottery.code == "A")
        )
        lottery_b = db.scalar(
            select(Lottery).where(Lottery.tenant_id == tenant_b.id, Lottery.code == "B")
        )
        assert lottery_a is not None
        assert lottery_b is not None

        db.add_all(
            [
                LotteryDraw(
                    lottery_id=lottery_a.id,
                    draw_number="A-1",
                    draw_date="2026-01-01",
                    main_numbers=[1, 2, 3],
                ),
                LotteryDraw(
                    lottery_id=lottery_b.id,
                    draw_number="B-1",
                    draw_date="2026-01-02",
                    main_numbers=[4, 5, 6],
                ),
            ]
        )
        db.commit()

        assert QuotaUsageService.get_current_usage(
            db, tenant_id=tenant_a.id, quota_code="memberships.max"
        ) == 1
        assert QuotaUsageService.get_current_usage(
            db, tenant_id=tenant_a.id, quota_code="lotteries.max"
        ) == 1
        assert QuotaUsageService.get_current_usage(
            db, tenant_id=tenant_a.id, quota_code="draws.max"
        ) == 1
        assert QuotaUsageService.get_current_usage(
            db, tenant_id=tenant_b.id, quota_code="draws.max"
        ) == 1


def test_unsupported_usage_quota_is_explicit() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        with pytest.raises(QuotaUsageNotSupportedError):
            QuotaUsageService.get_current_usage(
                db, tenant_id=1, quota_code="predictions.max"
            )

        with pytest.raises(QuotaUsageNotSupportedError):
            QuotaUsageService.get_current_usage(
                db, tenant_id=1, quota_code="ai_generations.monthly"
            )


def test_invalid_tenant_id_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        with pytest.raises(ValueError):
            QuotaUsageService.get_current_usage(
                db, tenant_id=0, quota_code="memberships.max"
            )
