import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.services.quota_service import QuotaNotConfiguredError
from app.services.quota_usage_service import QuotaUsageService


def test_consume_rejects_inactive_tenant_before_usage_mutation() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        plan = Plan(code="inactive-tenant", name="Inactive Tenant", is_active=True)
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
            name="Inactive Tenant",
            slug="inactive-tenant",
            plan_id=plan.id,
            is_active=False,
        )
        db.add(tenant)
        db.commit()

        with pytest.raises(QuotaNotConfiguredError):
            QuotaUsageService.consume(
                db,
                tenant_id=tenant.id,
                quota_code="predictions.max",
            )

        assert db.query(PlanQuota).count() == 1
        assert db.query(Tenant).filter(Tenant.id == tenant.id).one().is_active is False
