from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.lottery_draw import LotteryDraw


class DrawResult(Base):
    __tablename__ = "draw_results"

    __table_args__ = (
        UniqueConstraint(
            "draw_id",
            "group_code",
            "position",
            name="uq_draw_results_draw_group_position",
        ),
        Index(
            "ix_draw_results_draw_group_position",
            "draw_id",
            "group_code",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    draw_id: Mapped[int] = mapped_column(
        ForeignKey("lottery_draws.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_code: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(String(50), nullable=False)
    numeric_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    draw: Mapped["LotteryDraw"] = relationship(back_populates="results")
