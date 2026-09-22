from datetime import date, datetime, time

from fastapi import HTTPException

from app.scheduler.dated_schedule import DatedDrawTime, DatedSchedule
from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw, due_draws
from app.scheduler.runner import classify_ingestion_error
from app.sources.ingestion import SourceExtractionError, SourceNormalizationError


def test_scheduler_classifies_source_errors():
    assert classify_ingestion_error(SourceExtractionError("fetch failed")) == "SOURCE_ERROR"
    assert classify_ingestion_error(SourceNormalizationError("invalid result")) == "VALIDATION_ERROR"


def test_scheduler_classifies_duplicate_conflict():
    assert classify_ingestion_error(HTTPException(status_code=409, detail="duplicate")) == "DUPLICATE"


def test_scheduler_keeps_unknown_errors_isolated():
    assert classify_ingestion_error(RuntimeError("unexpected")) == "ERROR"


def test_dated_schedule_supports_super_astro_variable_times():
    schedule = DatedSchedule(
        (
            DatedDrawTime(date(2026, 9, 21), "ASTRO_SOL", time(13, 0)),
            DatedDrawTime(date(2026, 9, 21), "ASTRO_LUNA", time(22, 0)),
        )
    )
    assert schedule.is_due(
        datetime(2026, 9, 21, 13, 30, tzinfo=COLOMBIA_TZ),
        "ASTRO_SOL",
    )
    assert schedule.is_due(
        datetime(2026, 9, 21, 22, 45, tzinfo=COLOMBIA_TZ),
        "ASTRO_LUNA",
    )
    assert not schedule.is_due(
        datetime(2026, 9, 21, 12, 59, tzinfo=COLOMBIA_TZ),
        "ASTRO_SOL",
    )


def test_dated_schedule_rejects_duplicate_calendar_entries():
    schedule = DatedSchedule(
        (
            DatedDrawTime(date(2026, 9, 21), "ASTRO_SOL", time(13, 0)),
            DatedDrawTime(date(2026, 9, 21), "ASTRO_SOL", time(14, 0)),
        )
    )
    try:
        schedule.for_date(date(2026, 9, 21), "ASTRO_SOL")
    except ValueError as exc:
        assert "Duplicate dated schedule" in str(exc)
    else:
        raise AssertionError("Expected duplicate dated schedule to fail")


def test_fixed_schedule_remains_unpublished_outside_window():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30)
    assert due_draws(
        datetime(2026, 9, 21, 14, 0, tzinfo=COLOMBIA_TZ),
        schedules=(schedule,),
    ) == []
