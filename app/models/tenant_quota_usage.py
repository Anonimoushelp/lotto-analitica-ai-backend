from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantQuotaUsage(Base):
    __tablename__ = "tenant_quota_usages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "quota_code",
            "period_key",
            name="uq_tenant_quota_usages_scope",
        ),
        CheckConstraint("usage_value >= 0", name="ck_tenant_quota_usages_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quota_code: Mapped[str] = mapped_column(String(80), nullable=False)
    period_key: Mapped[str] = mapped_column(String(16), nullable=False)
    usage_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
