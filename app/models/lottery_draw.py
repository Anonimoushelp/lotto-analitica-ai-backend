from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.lottery import Lottery


DRAW_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class LotteryDraw(Base):
    __tablename__ = "lottery_draws"

    __table_args__ = (
        UniqueConstraint(
            "lottery_id",
            "draw_type",
            "draw_number",
            name="uq_lottery_draw_type_number",
        ),
        UniqueConstraint(
            "lottery_id",
            "draw_type",
            "draw_date",
            name="uq_lottery_draw_type_date",
        ),
        Index(
            "ix_lottery_draws_lottery_date_id",
            "lottery_id",
            "draw_date",
            "id",
        ),
        Index(
            "ix_lottery_draws_lottery_type_date",
            "lottery_id",
            "draw_type",
            "draw_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    lottery_id: Mapped[int] = mapped_column(
        ForeignKey("lotteries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    draw_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="DEFAULT",
        server_default="DEFAULT",
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

    draw_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    main_numbers: Mapped[list[int]] = mapped_column(
        DRAW_JSON_TYPE,
        nullable=False,
    )

    bonus_numbers: Mapped[list[int] | None] = mapped_column(
        DRAW_JSON_TYPE,
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        DRAW_JSON_TYPE,
        nullable=True,
    )

    validation_json: Mapped[dict[str, Any] | None] = mapped_column(
        DRAW_JSON_TYPE,
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
