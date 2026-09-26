from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from fastapi import HTTPException

from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw, expected_window
from app.sources.ingestion import SourceExtractionError, SourceNormalizationError
from app.sources.parsers import SourceParseError


class SchedulerStatus:
    NOT_PUBLISHED = "NOT_PUBLISHED"
    OUTSIDE_TOLERANCE = "OUTSIDE_TOLERANCE"
    SOURCE_ERROR = "SOURCE_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE = "DUPLICATE"
    SUCCESS = "SUCCESS"


@dataclass(frozen=True)
class IngestionAttempt:
    lottery_code: str
    draw_type: str
    status: str
    message: str


def _has_cause(exc: Exception, expected_type: type[Exception]) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, expected_type):
            return True
        current = current.__cause__ or current.__context__
    return False


def classify_ingestion_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException) and exc.status_code == 409:
        return SchedulerStatus.DUPLICATE
    if _has_cause(exc, SourceParseError):
        return SchedulerStatus.PARSE_ERROR
    if isinstance(exc, SourceNormalizationError):
        return SchedulerStatus.VALIDATION_ERROR
    if isinstance(exc, SourceExtractionError):
        return SchedulerStatus.SOURCE_ERROR
    return "ERROR"


def evaluate_schedule(schedule: ScheduledDraw, now: datetime, *, holiday_dates: frozenset[date] = frozenset()) -> str:
    current = now.astimezone(COLOMBIA_TZ)
    if not schedule.enabled or current.weekday() not in schedule.weekdays:
        return SchedulerStatus.NOT_PUBLISHED
    try:
        expected, end = expected_window(schedule, current.date(), holiday_dates=holiday_dates)
    except ValueError:
        return SchedulerStatus.NOT_PUBLISHED
    if current < expected:
        return SchedulerStatus.NOT_PUBLISHED
    if current > end:
        return SchedulerStatus.OUTSIDE_TOLERANCE
    return SchedulerStatus.SUCCESS


class SchedulerRunner:
    """Evaluate schedules, then ingest only draws whose window is SUCCESS."""

    def __init__(self, ingest: Callable[[str, str], str], *, schedules: tuple[ScheduledDraw, ...]) -> None:
        self.ingest = ingest
        self.schedules = schedules

    def run_once(self, now: datetime | None = None, *, holiday_dates: frozenset[date] = frozenset()) -> list[IngestionAttempt]:
        current = (now or datetime.now(COLOMBIA_TZ)).astimezone(COLOMBIA_TZ)
        grouped: dict[tuple[str, str], list[str]] = {}
        for scheduled in self.schedules:
            key = (scheduled.lottery_code, scheduled.draw_type)
            grouped.setdefault(key, []).append(evaluate_schedule(scheduled, current, holiday_dates=holiday_dates))

        attempts: list[IngestionAttempt] = []
        for key, statuses in grouped.items():
            if SchedulerStatus.SUCCESS not in statuses:
                status = SchedulerStatus.OUTSIDE_TOLERANCE if SchedulerStatus.OUTSIDE_TOLERANCE in statuses else SchedulerStatus.NOT_PUBLISHED
                attempts.append(IngestionAttempt(*key, status, "schedule not due"))
                continue
            try:
                message = self.ingest(*key)
            except Exception as exc:  # noqa: BLE001
                attempts.append(IngestionAttempt(*key, classify_ingestion_error(exc), str(exc)))
            else:
                attempts.append(IngestionAttempt(*key, SchedulerStatus.SUCCESS, message))
        return attempts
