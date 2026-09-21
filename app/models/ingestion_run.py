from typing import Any
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


INGESTION_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    draw_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(
        INGESTION_JSON_TYPE, nullable=True
    )
