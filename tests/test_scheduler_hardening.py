from datetime import date, datetime, time

import pytest
from fastapi import HTTPException

from app.scheduler.dated_schedule import DatedDrawTime, DatedSchedule
from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw, due_draws
from app.scheduler.runner import (
    SchedulerStatus,
    classify_ingestion_error,
    evaluate_schedule,
)
from app.sources.ingestion import SourceExtractionError, SourceNormalizationError
from app.sources.parsers import SourceParseError


def test_scheduler_classifies_source_errors():
    assert (
        classify_ingestion_error(SourceExtractionError("fetch failed"))
        == SchedulerStatus.SOURCE_ERROR
    )
    assert (
        classify_ingestion_error(SourceNormalizationError("invalid result"))
        == SchedulerStatus.VALIDATION_ERROR
    )


def test_scheduler_classifies_parse_errors_even_when_wrapped():
    wrapped = SourceExtractionError("extraction failed")
    wrapped.__cause__ = SourceParseError("invalid HTML")
    assert classify_ingestion_error(wrapped) == SchedulerStatus.PARSE_ERROR


def test_scheduler_classifies_duplicate_conflict():
    assert (
        classify_ingestion_error(
            HTTPException(status_code=409, detail="duplicate")
        )
        == SchedulerStatus.DUPLICATE
    )


def test_scheduler_keeps_unknown_errors_isolated():
    assert classify_ingestion_error(RuntimeError("unexpected")) == "ERROR"


def test_scheduler_explicit_status_before_and_after_window():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30)
    assert (
        evaluate_schedule(
            schedule,
            datetime(2026, 9, 21, 12, 59, tzinfo=COLOMBIA_TZ),
        )
        == SchedulerStatus.NOT_PUBLISHED
    )
    assert (
        evaluate_schedule(
            schedule,
            datetime(2026, 9, 21, 13, 15, tzinfo=COLOMBIA_TZ),
        )
        == SchedulerStatus.SUCCESS
    )
    assert (
        evaluate_schedule(
            schedule,
            datetime(2026, 9, 21, 13, 31, tzinfo=COLOMBIA_TZ),
        )
        == SchedulerStatus.OUTSIDE_TOLERANCE
    )


def test_scheduler_marks_non_scheduled_weekday_as_not_published():
    schedule = ScheduledDraw(
        "TEST",
        "DIA",
        time(13, 0),
        weekdays=frozenset({0}),
    )
    assert (
        evaluate_schedule(
            schedule,
            datetime(2026, 9, 22, 13, 10, tzinfo=COLOMBIA_TZ),
        )
        == SchedulerStatus.NOT_PUBLISHED
    )


def test_scheduler_isolates_same_lottery_different_draw_types():
    calls: list[tuple[str, str]] = []

    def ingest(lottery_code: str, draw_type: str) -> str:
        calls.append((lottery_code, draw_type))
        if draw_type == "DIA":
            raise HTTPException(status_code=409, detail="duplicate")
        return "persisted"

    schedules = (
        ScheduledDraw("TEST", "DIA", time(13, 0)),
        ScheduledDraw("TEST", "NOCHE", time(13, 0)),
    )
    runner = __import__("app.scheduler.runner", fromlist=["SchedulerRunner"]).SchedulerRunner(
        ingest,
        schedules=schedules,
    )
    attempts = runner.run_once(
        datetime(2026, 9, 21, 13, 10, tzinfo=COLOMBIA_TZ)
    )

    assert [attempt.status for attempt in attempts] == [
        SchedulerStatus.DUPLICATE,
        SchedulerStatus.SUCCESS,
    ]
    assert calls == [("TEST", "DIA"), ("TEST", "NOCHE")]


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
    with pytest.raises(ValueError, match="Duplicate dated schedule"):
        schedule.for_date(date(2026, 9, 21), "ASTRO_SOL"


def test_fixed_schedule_remains_unpublished_outside_window():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30)
    assert due_draws(
        datetime(2026, 9, 21, 14, 0, tzinfo=COLOMBIA_TZ),
        schedules=(schedule,),
    ) == []
