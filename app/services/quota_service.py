from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.quotas import QuotaCode
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant


class QuotaError(Exception):
    """Base exception for SaaS quota enforcement failures."""


class QuotaNotConfiguredError(QuotaError):
    """Raised when a tenant has no configured limit for a quota."""


class QuotaExceededError(QuotaError):
    """Raised when an operation would exceed the tenant's quota."""


class QuotaService:
    @staticmethod
    def lock_tenant(db: Session, *, tenant_id: int) -> None:
        """Serialize quota-enforced mutations for one active tenant transaction."""
        tenant_exists = db.scalar(
            select(Tenant.id)
            .where(
                Tenant.id == tenant_id,
                Tenant.is_active.is_(True),
            )
            .with_for_update()
        )
        if tenant_exists is None:
            raise QuotaNotConfiguredError(
                f"Active tenant {tenant_id} is not available for quota enforcement"
            )

    @staticmethod
    def get_limit(db: Session, *, tenant_id: int, quota_code: QuotaCode) -> int:
        limit = db.scalar(
            select(PlanQuota.limit_value)
            .join(Tenant, Tenant.plan_id == PlanQuota.plan_id)
            .join(Plan, Plan.id == PlanQuota.plan_id)
            .where(
                Tenant.id == tenant_id,
                Tenant.is_active.is_(True),
                Plan.is_active.is_(True),
                PlanQuota.quota_code == quota_code,
            )
        )
        if limit is None:
            raise QuotaNotConfiguredError(
                f"Quota '{quota_code}' is not configured for tenant {tenant_id}"
            )
        if limit < 0:
            raise QuotaNotConfiguredError(
                f"Quota '{quota_code}' has an invalid negative limit"
            )
        return int(limit)

    @staticmethod
    def enforce(
        db: Session,
        *,
        tenant_id: int,
        quota_code: QuotaCode,
        current_usage: int,
        increment: int = 1,
    ) -> int:
        if current_usage < 0:
            raise ValueError("current_usage must be non-negative")
        if increment <= 0:
            raise ValueError("increment must be positive")

        limit = QuotaService.get_limit(
            db,
            tenant_id=tenant_id,
            quota_code=quota_code,
        )
        projected_usage = current_usage + increment
        if projected_usage > limit:
            raise QuotaExceededError(
                f"Quota '{quota_code}' exceeded: "
                f"current={current_usage}, increment={increment}, limit={limit}"
            )
        return limit

    @staticmethod
    def enforce_if_configured(
        db: Session,
        *,
        tenant_id: int,
        quota_code: QuotaCode,
        current_usage: int,
        increment: int = 1,
    ) -> int | None:
        """Enforce configured quotas while tolerating legacy SQLite fixtures without SaaS tables."""
        try:
            return QuotaService.enforce(
                db,
                tenant_id=tenant_id,
                quota_code=quota_code,
                current_usage=current_usage,
                increment=increment,
            )
        except QuotaNotConfiguredError:
            return None
        except OperationalError as exc:
            if db.bind is not None and db.bind.dialect.name == "sqlite" and "no such table: plan_quotas" in str(exc):
                db.rollback()
                return None
            raise
