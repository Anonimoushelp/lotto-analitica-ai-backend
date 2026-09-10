from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.models.user import User
from app.services.quota_service import QuotaExceededError
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
        user_a = User(email="a@example.com", password_hash=hash_password("StrongTestPassword123!"), is_active=True)
        user_b = User(email="b@example.com", password_hash=hash_password("StrongTestPassword123!"), is_active=True)
        db.add_all([tenant_a, tenant_b, user_a, user_b])
        db.flush()
        db.add_all([
            Membership(tenant_id=tenant_a.id, user_id=user_a.id, role="admin"),
            Membership(tenant_id=tenant_b.id, user_id=user_b.id, role="admin"),
            Membership(tenant_id=tenant_a.id, user_id=user_b.id, role="viewer", is_active=False),
            Lottery(tenant_id=tenant_a.id, code="A", name="Lottery A", country="CO", active=True),
            Lottery(tenant_id=tenant_a.id, code="A-INACTIVE", name="Lottery A inactive", country="CO", active=False),
            Lottery(tenant_id=tenant_b.id, code="B", name="Lottery B", country="CO", active=True),
        ])
        db.flush()
        lottery_a = db.scalar(select(Lottery).where(Lottery.tenant_id == tenant_a.id, Lottery.code == "A"))
        lottery_b = db.scalar(select(Lottery).where(Lottery.tenant_id == tenant_b.id, Lottery.code == "B"))
        assert lottery_a is not None
        assert lottery_b is not None
        db.add_all([
            LotteryDraw(lottery_id=lottery_a.id, draw_number="A-1", draw_date=date(2026, 1, 1), main_numbers=[1, 2, 3]),
            LotteryDraw(lottery_id=lottery_b.id, draw_number="B-1", draw_date=date(2026, 1, 2), main_numbers=[4, 5, 6]),
        ])
        db.commit()
        assert QuotaUsageService.get_current_usage(db, tenant_id=tenant_a.id, quota_code="memberships.max") == 1
        assert QuotaUsageService.get_current_usage(db, tenant_id=tenant_a.id, quota_code="lotteries.max") == 1
        assert QuotaUsageService.get_current_usage(db, tenant_id=tenant_a.id, quota_code="draws.max") == 1
        assert QuotaUsageService.get_current_usage(db, tenant_id=tenant_b.id, quota_code="draws.max") == 1


def test_unsupported_usage_quota_is_explicit() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(QuotaUsageNotSupportedError):
            QuotaUsageService.get_current_usage(db, tenant_id=1, quota_code="predictions.max")
        with pytest.raises(QuotaUsageNotSupportedError):
            QuotaUsageService.get_current_usage(db, tenant_id=1, quota_code="ai_generations.monthly")


def test_invalid_tenant_id_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db, pytest.raises(ValueError):
        QuotaUsageService.get_current_usage(db, tenant_id=0, quota_code="memberships.max")


def test_consume_predictions_uses_lifetime_ledger() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        plan = Plan(code="prediction-test", name="Prediction Test", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="predictions.max", limit_value=3))
        tenant = Tenant(name="Prediction Tenant", slug="prediction-tenant", plan_id=plan.id, is_active=True)
        db.add(tenant)
        db.commit()
        first = QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="predictions.max")
        second = QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="predictions.max", increment=2)
        db.commit()
        assert first == 1
        assert second == 3
        usage = db.scalar(select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant.id, TenantQuotaUsage.quota_code == "predictions.max", TenantQuotaUsage.period_key == "lifetime"))
        assert usage is not None
        assert usage.usage_value == 3


def test_consume_ai_generations_rolls_over_monthly_period() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        plan = Plan(code="ai-test", name="AI Test", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="ai_generations.monthly", limit_value=2))
        tenant = Tenant(name="AI Tenant", slug="ai-tenant", plan_id=plan.id, is_active=True)
        db.add(tenant)
        db.commit()
        january = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
        february = datetime(2026, 2, 1, 0, 1, tzinfo=UTC)
        assert QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="ai_generations.monthly", now=january) == 1
        assert QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="ai_generations.monthly", now=january) == 2
        assert QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="ai_generations.monthly", now=february) == 1
        db.commit()
        rows = db.scalars(select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant.id, TenantQuotaUsage.quota_code == "ai_generations.monthly")).all()
        assert {(row.period_key, row.usage_value) for row in rows} == {("2026-01", 2), ("2026-02", 1)}


def test_consume_rejects_quota_overflow_without_increment() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        plan = Plan(code="limit-test", name="Limit Test", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="predictions.max", limit_value=1))
        tenant = Tenant(name="Limit Tenant", slug="limit-tenant", plan_id=plan.id, is_active=True)
        db.add(tenant)
        db.commit()
        assert QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="predictions.max") == 1
        db.commit()
        with pytest.raises(QuotaExceededError):
            QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="predictions.max")
        db.rollback()
        usage = db.scalar(select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant.id, TenantQuotaUsage.quota_code == "predictions.max", TenantQuotaUsage.period_key == "lifetime"))
        assert usage is not None
        assert usage.usage_value == 1


def test_consume_rolls_back_with_outer_transaction_failure() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        plan = Plan(code="rollback-test", name="Rollback Test", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="predictions.max", limit_value=3))
        tenant = Tenant(name="Rollback Tenant", slug="rollback-tenant", plan_id=plan.id, is_active=True)
        db.add(tenant)
        db.commit()
        QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="predictions.max", increment=2)
        db.rollback()
        usage = db.scalar(select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant.id, TenantQuotaUsage.quota_code == "predictions.max", TenantQuotaUsage.period_key == "lifetime"))
        assert usage is None


def test_ledger_usage_isolated_between_tenants() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        plan = Plan(code="ledger-isolation", name="Ledger Isolation", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="predictions.max", limit_value=3))
        tenant_a = Tenant(name="Ledger Tenant A", slug="ledger-tenant-a", plan_id=plan.id, is_active=True)
        tenant_b = Tenant(name="Ledger Tenant B", slug="ledger-tenant-b", plan_id=plan.id, is_active=True)
        db.add_all([tenant_a, tenant_b])
        db.commit()
        assert QuotaUsageService.consume(db, tenant_id=tenant_a.id, quota_code="predictions.max", increment=2) == 2
        assert QuotaUsageService.consume(db, tenant_id=tenant_b.id, quota_code="predictions.max") == 1
        db.commit()
        usages = db.scalars(select(TenantQuotaUsage).where(TenantQuotaUsage.quota_code == "predictions.max", TenantQuotaUsage.period_key == "lifetime")).all()
        assert {(usage.tenant_id, usage.usage_value) for usage in usages} == {(tenant_a.id, 2), (tenant_b.id, 1)}


def test_consume_rejects_non_ledger_quota_before_mutation() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        plan = Plan(code="unsupported-consume", name="Unsupported Consume", is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlanQuota(plan_id=plan.id, quota_code="memberships.max", limit_value=3))
        tenant = Tenant(name="Unsupported Tenant", slug="unsupported-tenant", plan_id=plan.id, is_active=True)
        db.add(tenant)
        db.commit()
        with pytest.raises(QuotaUsageNotSupportedError):
            QuotaUsageService.consume(db, tenant_id=tenant.id, quota_code="memberships.max")
        assert db.scalar(select(TenantQuotaUsage)) is None
