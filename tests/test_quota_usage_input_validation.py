import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.services.quota_usage_service import QuotaUsageService


@pytest.mark.parametrize("increment", [0, -1])
def test_consume_rejects_non_positive_increment_without_usage_mutation(
    increment: int,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        plan = Plan(code="input-validation", name="Input Validation", is_active=True)
        db.add(plan)
        db.flush()
        db.add(
            PlanQuota(
                plan_id=plan.id,
                quota_code="predictions.max",
                limit_value=3,
            )
        )
        tenant = Tenant(
            name="Input Validation Tenant",
            slug="input-validation-tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()

        with pytest.raises(ValueError, match="increment must be positive"):
            QuotaUsageService.consume(
                db,
                tenant_id=tenant.id,
                quota_code="predictions.max",
                increment=increment,
            )

        assert db.scalar(select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant.id)) is None
