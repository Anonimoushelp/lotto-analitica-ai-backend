from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.services.quota_service import QuotaExceededError
from app.services.quota_usage_service import (
    QuotaUsageNotSupportedError,
    QuotaUsageService,
)


def _seed_tenant(db: Session, *, prediction_limit: int = 2, ai_limit: int = 2) -> int:
    plan = Plan(code="boundary-tests", name="Boundary Tests", is_active=True)
    db.add(plan)
    db.flush()
    db.add_all(
        [
            PlanQuota(
                plan_id=plan.id,
                quota_code="predictions.max",
                limit_value=prediction_limit,
            ),
            PlanQuota(
                plan_id=plan.id,
                quota_code="ai_generations.monthly",
                limit_value=ai_limit,
            ),
        ]
    )
    tenant = Tenant(
        name="Boundary Tenant",
        slug="boundary-tenant",
        plan_id=plan.id,
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    return tenant.id


def test_consume_allows_exact_limit_then_rejects_overage_without_increment() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id = _seed_tenant(db, prediction_limit=2)

        assert (
            QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code="predictions.max",
                increment=2,
            )
            == 2
        )
        db.commit()

        with pytest.raises(QuotaExceededError, match="exceeded"):
            QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code="predictions.max",
            )

        db.rollback()
        usage = db.scalar(select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant_id))
        assert usage is not None
        assert usage.usage_value == 2


def test_consume_rejects_unsupported_ledger_code_without_usage_mutation() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id = _seed_tenant(db)

        with pytest.raises(QuotaUsageNotSupportedError):
            QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code="draws.max",
            )

        assert db.scalars(select(TenantQuotaUsage)).all() == []


def test_ai_generation_usage_rolls_over_to_new_month() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id = _seed_tenant(db, ai_limit=2)
        december = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
        january = datetime(2027, 1, 1, 0, 1, tzinfo=UTC)

        assert (
            QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code="ai_generations.monthly",
                increment=2,
                now=december,
            )
            == 2
        )
        db.commit()

        with pytest.raises(QuotaExceededError):
            QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code="ai_generations.monthly",
                now=december,
            )
        db.rollback()

        assert (
            QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code="ai_generations.monthly",
                now=january,
            )
            == 1
        )
        db.commit()

        usages = db.scalars(
            select(TenantQuotaUsage)
            .where(TenantQuotaUsage.tenant_id == tenant_id)
            .order_by(TenantQuotaUsage.period_key)
        ).all()
        assert [(item.period_key, item.usage_value) for item in usages] == [
            ("2026-12", 2),
            ("2027-01", 1),
        ]
