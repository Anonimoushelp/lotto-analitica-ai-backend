from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.quotas import QuotaCode
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.services.quota_service import (
    QuotaExceededError,
    QuotaNotConfiguredError,
    QuotaService,
)


class QuotaUsageNotSupportedError(ValueError):
    """Raised when a quota requires usage tracking not yet persisted."""


class QuotaUsageService:
    """Resolve and mutate persisted, tenant-scoped quota usage."""

    @staticmethod
    def get_current_usage(
        db: Session,
        *,
        tenant_id: int,
        quota_code: QuotaCode,
    ) -> int:
        if tenant_id <= 0:
            raise ValueError("tenant_id must be positive")

        if quota_code not in {"memberships.max", "lotteries.max", "draws.max"}:
            raise QuotaUsageNotSupportedError(
                f"Usage tracking for quota '{quota_code}' is not persisted yet"
            )

        QuotaService.lock_tenant(db, tenant_id=tenant_id)

        if quota_code == "memberships.max":
            return int(
                db.scalar(
                    select(func.count(Membership.id)).where(
                        Membership.tenant_id == tenant_id,
                        Membership.is_active.is_(True),
                    )
                )
                or 0
            )

        if quota_code == "lotteries.max":
            return int(
                db.scalar(
                    select(func.count(Lottery.id)).where(
                        Lottery.tenant_id == tenant_id,
                        Lottery.active.is_(True),
                    )
                )
                or 0
            )

        return int(
            db.scalar(
                select(func.count(LotteryDraw.id))
                .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
                .where(Lottery.tenant_id == tenant_id)
            )
            or 0
        )

    @staticmethod
    def _period_key(quota_code: QuotaCode, now: datetime) -> str:
        if quota_code == "predictions.max":
            return "lifetime"
        if quota_code == "ai_generations.monthly":
            return now.strftime("%Y-%m")
        raise QuotaUsageNotSupportedError(
            f"Ledger tracking for quota '{quota_code}' is not supported"
        )

    @staticmethod
    def consume(
        db: Session,
        *,
        tenant_id: int,
        quota_code: QuotaCode,
        increment: int = 1,
        now: datetime | None = None,
    ) -> int:
        """Atomically consume ledger-backed quota within the caller's transaction."""
        if tenant_id <= 0:
            raise ValueError("tenant_id must be positive")
        if increment <= 0:
            raise ValueError("increment must be positive")

        current_time = now or datetime.now(UTC)
        period_key = QuotaUsageService._period_key(quota_code, current_time)
        QuotaService.lock_tenant(db, tenant_id=tenant_id)
        limit = QuotaService.get_limit(
            db,
            tenant_id=tenant_id,
            quota_code=quota_code,
        )

        usage = db.scalar(
            select(TenantQuotaUsage)
            .where(
                TenantQuotaUsage.tenant_id == tenant_id,
                TenantQuotaUsage.quota_code == quota_code,
                TenantQuotaUsage.period_key == period_key,
            )
            .with_for_update()
        )
        current_usage = usage.usage_value if usage is not None else 0
        projected_usage = current_usage + increment
        if projected_usage > limit:
            raise QuotaExceededError(
                f"Quota '{quota_code}' exceeded: "
                f"current={current_usage}, increment={increment}, limit={limit}"
            )

        if usage is None:
            usage = TenantQuotaUsage(
                tenant_id=tenant_id,
                quota_code=quota_code,
                period_key=period_key,
                usage_value=0,
            )
            db.add(usage)

        usage.usage_value = projected_usage
        db.flush()
        return projected_usage

    @staticmethod
    def consume_if_configured(
        db: Session,
        *,
        tenant_id: int,
        quota_code: QuotaCode,
        increment: int = 1,
        now: datetime | None = None,
    ) -> int | None:
        """Consume configured ledger quotas while tolerating legacy SQLite fixtures."""
        try:
            return QuotaUsageService.consume(
                db,
                tenant_id=tenant_id,
                quota_code=quota_code,
                increment=increment,
                now=now,
            )
        except QuotaNotConfiguredError:
            return None
        except OperationalError as exc:
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                message = str(exc)
                missing_tables = {
                    "no such table: plan_quotas",
                    "no such table: tenant_quota_usages",
                }
                if any(error in message for error in missing_tables):
                    db.rollback()
                    return None
            raise
