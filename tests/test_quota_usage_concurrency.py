import os
import threading

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.services.quota_service import QuotaExceededError
from app.services.quota_usage_service import QuotaUsageService


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="concurrency locking test requires PostgreSQL",
)
def test_concurrent_consumption_cannot_exceed_quota() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=4, max_overflow=0)

    with Session(engine) as db:
        plan = Plan(code="concurrency", name="Concurrency", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="predictions.max", limit_value=1))
        tenant = Tenant(
            name="Concurrency Tenant",
            slug="concurrency-tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()
        tenant_id = tenant.id

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def consume() -> None:
        with Session(engine) as db:
            barrier.wait()
            try:
                QuotaUsageService.consume(
                    db,
                    tenant_id=tenant_id,
                    quota_code="predictions.max",
                )
                db.commit()
                result = "success"
            except QuotaExceededError:
                db.rollback()
                result = "exceeded"
            with lock:
                results.append(result)

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == ["exceeded", "success"]

    with Session(engine) as db:
        usage = db.scalar(
            select(TenantQuotaUsage).where(
                TenantQuotaUsage.tenant_id == tenant_id,
                TenantQuotaUsage.quota_code == "predictions.max",
                TenantQuotaUsage.period_key == "lifetime",
            )
        )
        assert usage is not None
        assert usage.usage_value == 1
