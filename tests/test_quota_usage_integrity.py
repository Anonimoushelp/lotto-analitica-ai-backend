import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.plan import Plan
from app.models.tenant import Tenant
from app.models.tenant_quota_usage import TenantQuotaUsage


def test_tenant_quota_usage_rejects_negative_value_at_database_constraint():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        plan = Plan(code="usage-integrity", name="Usage Integrity", is_active=True)
        db.add(plan)
        db.flush()

        tenant = Tenant(
            name="Usage Integrity Tenant",
            slug="usage-integrity-tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.flush()

        db.add(
            TenantQuotaUsage(
                tenant_id=tenant.id,
                quota_code="predictions.max",
                period_key="lifetime",
                usage_value=-1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
