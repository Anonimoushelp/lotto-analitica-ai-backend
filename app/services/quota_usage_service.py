from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.quotas import QuotaCode
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership


class QuotaUsageNotSupportedError(ValueError):
    """Raised when a quota requires usage tracking not yet persisted."""


class QuotaUsageService:
    """Resolve persisted, tenant-scoped usage for count-based quotas."""

    @staticmethod
    def get_current_usage(
        db: Session,
        *,
        tenant_id: int,
        quota_code: QuotaCode,
    ) -> int:
        if tenant_id <= 0:
            raise ValueError("tenant_id must be positive")

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

        if quota_code == "draws.max":
            return int(
                db.scalar(
                    select(func.count(LotteryDraw.id))
                    .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
                    .where(Lottery.tenant_id == tenant_id)
                )
                or 0
            )

        raise QuotaUsageNotSupportedError(
            f"Usage tracking for quota '{quota_code}' is not persisted yet"
        )
