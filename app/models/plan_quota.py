from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.plan import Plan


class PlanQuota(Base):
    __tablename__ = "plan_quotas"
    __table_args__ = (
        UniqueConstraint("plan_id", "quota_code", name="uq_plan_quotas_plan_code"),
        CheckConstraint("limit_value >= 0", name="ck_plan_quotas_limit_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quota_code: Mapped[str] = mapped_column(String(80), nullable=False)
    limit_value: Mapped[int] = mapped_column(BigInteger, nullable=False)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="quotas")
