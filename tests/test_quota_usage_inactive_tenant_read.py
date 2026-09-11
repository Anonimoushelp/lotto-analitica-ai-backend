import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.plan import Plan
from app.models.tenant import Tenant
from app.services.quota_service import QuotaNotConfiguredError
from app.services.quota_usage_service import QuotaUsageService


def test_current_usage_rejects_inactive_tenant() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        plan = Plan(code="inactive-read", name="Inactive Read", is_active=True)
        db.add(plan)
        db.flush()
        tenant = Tenant(
            name="Inactive Read Tenant",
            slug="inactive-read-tenant",
            plan_id=plan.id,
            is_active=False,
        )
        db.add(tenant)
        db.commit()

        with pytest.raises(QuotaNotConfiguredError):
            QuotaUsageService.get_current_usage(
                db,
                tenant_id=tenant.id,
                quota_code="memberships.max",
            )
