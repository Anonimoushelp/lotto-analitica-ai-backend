from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.lottery import Lottery


JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class LotteryRule(Base):
    __tablename__ = "lottery_rules"

    __table_args__ = (
        UniqueConstraint(
            "lottery_id",
            "version",
            name="uq_lottery_rules_lottery_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    lottery_id: Mapped[int] = mapped_column(
        ForeignKey("lotteries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    lottery: Mapped["Lottery"] = relationship(back_populates="rules")
