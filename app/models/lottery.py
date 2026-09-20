from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.lottery_draw import LotteryDraw
    from app.models.lottery_rule import LotteryRule


JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Lottery(Base):
    __tablename__ = "lotteries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    modality_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="lotto",
        index=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="America/Bogota",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_TYPE,
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

    draws: Mapped[list["LotteryDraw"]] = relationship(
        back_populates="lottery",
        cascade="all, delete-orphan",
    )

    rules: Mapped[list["LotteryRule"]] = relationship(
        back_populates="lottery",
        cascade="all, delete-orphan",
        order_by="LotteryRule.version.desc()",
    )
