import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.quotas import ALL_QUOTA_CODES
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.services.quota_service import (
    QuotaExceededError,
    QuotaNotConfiguredError,
    QuotaService,
)


def test_quota_catalog_contains_only_supported_codes():
    assert ALL_QUOTA_CODES == frozenset(
        {
            "memberships.max",
            "lotteries.max",
            "draws.max",
            "predictions.max",
            "ai_generations.monthly",
        }
    )


def test_quota_service_resolves_limit_from_tenant_plan():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    PlanQuota.__table__.create(engine)
    Tenant.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="test", name="Test", is_active=True)
        db.add(plan)
        db.flush()
        db.add(
            PlanQuota(
                plan_id=plan.id,
                quota_code="memberships.max",
                limit_value=5,
            )
        )
        tenant = Tenant(
            name="Tenant",
            slug="tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()

        assert (
            QuotaService.get_limit(
                db,
                tenant_id=tenant.id,
                quota_code="memberships.max",
            )
            == 5
        )

    Tenant.__table__.drop(engine)
    PlanQuota.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_quota_service_rejects_quota_from_inactive_plan():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    PlanQuota.__table__.create(engine)
    Tenant.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="inactive", name="Inactive", is_active=False)
        db.add(plan)
        db.flush()
        db.add(
            PlanQuota(
                plan_id=plan.id,
                quota_code="memberships.max",
                limit_value=5,
            )
        )
        tenant = Tenant(
            name="Tenant",
            slug="inactive-plan-tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()

        with pytest.raises(QuotaNotConfiguredError):
            QuotaService.get_limit(
                db,
                tenant_id=tenant.id,
                quota_code="memberships.max",
            )

    Tenant.__table__.drop(engine)
    PlanQuota.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_plan_quota_rejects_negative_limit_at_database_constraint():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    PlanQuota.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="negative-limit", name="Negative Limit", is_active=True)
        db.add(plan)
        db.flush()
        db.add(
            PlanQuota(
                plan_id=plan.id,
                quota_code="draws.max",
                limit_value=-1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()

    PlanQuota.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_quota_service_rejects_missing_quota():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    PlanQuota.__table__.create(engine)
    Tenant.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="test", name="Test", is_active=True)
        db.add(plan)
        db.flush()
        tenant = Tenant(
            name="Tenant",
            slug="tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()

        with pytest.raises(QuotaNotConfiguredError):
            QuotaService.get_limit(
                db,
                tenant_id=tenant.id,
                quota_code="lotteries.max",
            )

    Tenant.__table__.drop(engine)
    PlanQuota.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_quota_service_locks_active_tenant_for_quota_mutation():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    Tenant.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="lock-test", name="Lock Test", is_active=True)
        db.add(plan)
        db.flush()
        tenant = Tenant(
            name="Tenant",
            slug="tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()

        QuotaService.lock_tenant(db, tenant_id=tenant.id)
        assert db.in_transaction()

    Tenant.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_quota_service_does_not_lock_inactive_tenant():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    Tenant.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="inactive-lock-test", name="Inactive Lock Test", is_active=True)
        db.add(plan)
        db.flush()
        tenant = Tenant(
            name="Tenant",
            slug="tenant",
            plan_id=plan.id,
            is_active=False,
        )
        db.add(tenant)
        db.commit()

        with pytest.raises(QuotaNotConfiguredError):
            QuotaService.lock_tenant(db, tenant_id=tenant.id)

    Tenant.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_quota_service_enforces_projected_usage():
    engine = create_engine("sqlite:///:memory:")
    Plan.__table__.create(engine)
    PlanQuota.__table__.create(engine)
    Tenant.__table__.create(engine)

    with Session(engine) as db:
        plan = Plan(code="test", name="Test", is_active=True)
        db.add(plan)
        db.flush()
        db.add(
            PlanQuota(
                plan_id=plan.id,
                quota_code="draws.max",
                limit_value=10,
            )
        )
        tenant = Tenant(
            name="Tenant",
            slug="tenant",
            plan_id=plan.id,
            is_active=True,
        )
        db.add(tenant)
        db.commit()

        assert (
            QuotaService.enforce(
                db,
                tenant_id=tenant.id,
                quota_code="draws.max",
                current_usage=8,
                increment=2,
            )
            == 10
        )
        with pytest.raises(QuotaExceededError):
            QuotaService.enforce(
                db,
                tenant_id=tenant.id,
                quota_code="draws.max",
                current_usage=10,
            )

    Tenant.__table__.drop(engine)
    PlanQuota.__table__.drop(engine)
    Plan.__table__.drop(engine)


def test_quota_service_rejects_invalid_usage_arguments():
    with pytest.raises(ValueError):
        QuotaService.enforce(
            db=None,
            tenant_id=1,
            quota_code="draws.max",
            current_usage=-1,
        )

    with pytest.raises(ValueError):
        QuotaService.enforce(
            db=None,
            tenant_id=1,
            quota_code="draws.max",
            current_usage=0,
            increment=0,
        )
