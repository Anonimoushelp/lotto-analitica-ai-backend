from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionScheduleState(Base):
    __tablename__ = "ingestion_schedule_states"

    job_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_id: Mapped[str | None] = mapped_column(String(36))
    last_status: Mapped[str | None] = mapped_column(String(32))
    last_attempts: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
