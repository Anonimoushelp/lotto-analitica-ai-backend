from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException

from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw, due_draws
from app.sources.ingestion import SourceExtractionError, SourceNormalizationError


@dataclass(frozen=True)
class IngestionAttempt:
    lottery_code: str
    draw_type: str
    status: str
    message: str


def classify_ingestion_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException) and exc.status_code == 409:
        return "DUPLICATE"
    if isinstance(exc, SourceExtractionError):
        return "SOURCE_ERROR"
    if isinstance(exc, SourceNormalizationError):
        return "VALIDATION_ERROR"
    return "ERROR"


class SchedulerRunner:
    """Determine due draws and delegate each lottery/draw_type independently."""

    def __init__(
        self,
        ingest: Callable[[str, str], str],
        *,
        schedules: tuple[ScheduledDraw, ...],
    ) -> None:
        self.ingest = ingest
        self.schedules = schedules

    def run_once(self, now: datetime | None = None) -> list[IngestionAttempt]:
        current = (now or datetime.now(COLOMBIA_TZ)).astimezone(COLOMBIA_TZ)
        attempts: list[IngestionAttempt] = []
        seen: set[tuple[str, str]] = set()

        for scheduled in due_draws(current, schedules=self.schedules):
            key = (scheduled.lottery_code, scheduled.draw_type)
            if key in seen:
                continue
            seen.add(key)
            try:
                message = self.ingest(*key)
            except Exception as exc:  # noqa: BLE001 - isolate one scheduled draw failure
                attempts.append(
                    IngestionAttempt(*key, classify_ingestion_error(exc), str(exc))
                )
            else:
                attempts.append(IngestionAttempt(*key, "SUCCESS", message))

        return attempts
