from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.lottery import Lottery


class LotteryDraw(Base):
    __tablename__ = "lottery_draws"

    __table_args__ = (
        UniqueConstraint(
            "lottery_id",
            "draw_number",
            name="uq_lottery_draw_number",
        ),
        UniqueConstraint(
            "lottery_id",
            "draw_date",
            name="uq_lottery_draw_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    lottery_id: Mapped[int] = mapped_column(
        ForeignKey("lotteries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    draw_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    draw_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    main_numbers: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
    )

    bonus_numbers: Mapped[list[int] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    lottery: Mapped["Lottery"] = relationship(
        back_populates="draws",
    )
