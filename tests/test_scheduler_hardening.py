from datetime import date, datetime, time

import pytest
from fastapi import HTTPException

from app.scheduler.catalog_integration import (
    build_catalog_scheduler_bindings,
    ready_catalog_schedules,
)
from app.scheduler.dated_schedule import DatedDrawTime, DatedSchedule
from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw
from app.scheduler.runner import (
    SchedulerRunner,
    SchedulerStatus,
    classify_ingestion_error,
    evaluate_schedule,
)
from app.sources.ingestion import SourceExtractionError, SourceNormalizationError
from app.sources.parsers import SourceParseError
from scripts.run_scheduler import build_ingest_executor, FAILURE_STATUSES


def test_scheduler_classifies_source_errors():
    assert classify_ingestion_error(SourceExtractionError("fetch failed")) == SchedulerStatus.SOURCE_ERROR
    assert classify_ingestion_error(SourceNormalizationError("invalid result")) == SchedulerStatus.VALIDATION_ERROR


def test_scheduler_classifies_parse_errors_even_when_wrapped():
    wrapped = SourceExtractionError("extraction failed")
    wrapped.__cause__ = SourceParseError("invalid HTML")
    assert classify_ingestion_error(wrapped) == SchedulerStatus.PARSE_ERROR


def test_scheduler_classifies_duplicate_conflict():
    assert classify_ingestion_error(HTTPException(status_code=409, detail="duplicate")) == SchedulerStatus.DUPLICATE


def test_scheduler_keeps_unknown_errors_isolated():
    assert classify_ingestion_error(RuntimeError("unexpected")) == "ERROR"


def test_scheduler_explicit_status_before_and_after_window():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30)
    assert evaluate_schedule(
        schedule, datetime(2026, 9, 21, 12, 59, tzinfo=COLOMBIA_TZ)
    ) == SchedulerStatus.NOT_PUBLISHED
    assert evaluate_schedule(
        schedule, datetime(2026, 9, 21, 13, 15, tzinfo=COLOMBIA_TZ)
    ) == SchedulerStatus.SUCCESS
    assert evaluate_schedule(
        schedule, datetime(2026, 9, 21, 13, 31, tzinfo=COLOMBIA_TZ)
    ) == SchedulerStatus.OUTSIDE_TOLERANCE


def test_scheduler_marks_non_scheduled_weekday_as_not_published():
    schedule = ScheduledDraw(
        "TEST", "DIA", time(13, 0), weekdays=frozenset({0})
    )
    assert evaluate_schedule(
        schedule, datetime(2026, 9, 22, 13, 10, tzinfo=COLOMBIA_TZ)
    ) == SchedulerStatus.NOT_PUBLISHED


def test_runner_reports_not_published_and_does_not_ingest():
    calls: list[tuple[str, str]] = []
    runner = SchedulerRunner(
        lambda code, draw: calls.append((code, draw)) or "persisted",
        schedules=(ScheduledDraw("TEST", "DIA", time(13, 0)),),
    )
    attempts = runner.run_once(
        datetime(2026, 9, 21, 12, 59, tzinfo=COLOMBIA_TZ)
    )
    assert attempts[0].status == SchedulerStatus.NOT_PUBLISHED
    assert calls == []


def test_runner_reports_outside_tolerance_and_does_not_ingest():
    calls: list[tuple[str, str]] = []
    runner = SchedulerRunner(
        lambda code, draw: calls.append((code, draw)) or "persisted",
        schedules=(ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30),),
    )
    attempts = runner.run_once(
        datetime(2026, 9, 21, 14, 0, tzinfo=COLOMBIA_TZ)
    )
    assert attempts[0].status == SchedulerStatus.OUTSIDE_TOLERANCE
    assert calls == []


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
    attempts = SchedulerRunner(ingest, schedules=schedules).run_once(
        datetime(2026, 9, 21, 13, 10, tzinfo=COLOMBIA_TZ)
    )
    assert [attempt.status for attempt in attempts] == [
        SchedulerStatus.DUPLICATE,
        SchedulerStatus.SUCCESS,
    ]
    assert calls == [("TEST", "DIA"), ("TEST", "NOCHE")]


def test_calendar_only_catalog_schedule_is_executable_on_official_weekday():
    bindings = build_catalog_scheduler_bindings()
    schedules = ready_catalog_schedules(bindings)
    risaralda = next(
        item for item in schedules if item.lottery_code == "LOTERIA_RISARALDA"
    )
    assert risaralda.calendar_only is True
    calls: list[tuple[str, str]] = []
    attempts = SchedulerRunner(
        lambda code, draw: calls.append((code, draw)) or "controlled",
        schedules=(risaralda,),
    ).run_once(datetime(2026, 9, 25, 10, 0, tzinfo=COLOMBIA_TZ)
    )
    assert attempts[0].status == SchedulerStatus.SUCCESS
    assert calls == [("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")]


def test_catalog_scheduler_only_exposes_verified_ready_sources():
    bindings = build_catalog_scheduler_bindings()
    ready = {
        item.lottery_code
        for item in bindings
        if item.calendar_rule in ready_catalog_schedules(bindings)
    }
    assert "LOTERIA_RISARALDA" in ready
    assert "LOTERIA_META" not in ready
    assert "LOTERIA_QUINDIO" not in ready
    assert "EXTRA_COLOMBIA" not in ready


def test_holiday_schedule_reaches_runner():
    schedule = ScheduledDraw(
        "TEST",
        "NOCHE",
        time(19, 25),
        frozenset({6}),
        90,
        holiday_times=(time(19, 28),),
        skip_on_holiday=True,
    )
    calls: list[tuple[str, str]] = []
    attempts = SchedulerRunner(
        lambda code, draw: calls.append((code, draw)) or "holiday",
        schedules=(schedule,),
    ).run_once(
        datetime(2026, 9, 27, 19, 29, tzinfo=COLOMBIA_TZ),
        holiday_dates=frozenset({date(2026, 9, 27)}),
    )
    assert attempts[0].status == SchedulerStatus.SUCCESS
    assert calls == [("TEST", "NOCHE")]


def test_dated_schedule_supports_super_astro_variable_times():
    schedule = DatedSchedule(
        (
            DatedDrawTime(date(2026, 9, 21), "ASTRO_SOL", time(13, 0)),
            DatedDrawTime(date(2026, 9, 21), "ASTRO_LUNA", time(22, 0)),
        )
    )
    assert schedule.is_due(
        datetime(2026, 9, 21, 13, 30, tzinfo=COLOMBIA_TZ), "ASTRO_SOL"
    )
    assert schedule.is_due(
        datetime(2026, 9, 21, 22, 45, tzinfo=COLOMBIA_TZ), "ASTRO_LUNA"
    )
    assert not schedule.is_due(
        datetime(2026, 9, 21, 12, 59, tzinfo=COLOMBIA_TZ), "ASTRO_SOL"
    )


def test_dated_schedule_rejects_duplicate_calendar_entries():
    schedule = DatedSchedule(
        (
            DatedDrawTime(date(2026, 9, 21), "ASTRO_SOL", time(13, 0)),
            DatedDrawTime(date(2026, 9, 21), "ASTRO_SOL", time(14, 0)),
        )
    )
    with pytest.raises(ValueError, match="Duplicate dated schedule"):
        schedule.for_date(date(2026, 9, 21), "ASTRO_SOL")


def test_fixed_schedule_remains_outside_window():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30)
    attempts = SchedulerRunner(
        lambda *_: "persisted", schedules=(schedule,)
    ).run_once(datetime(2026, 9, 21, 14, 0, tzinfo=COLOMBIA_TZ))
    assert attempts[0].status == SchedulerStatus.OUTSIDE_TOLERANCE


def test_scheduler_script_keeps_ingestion_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLE_INGESTION", raising=False)
    executor = build_ingest_executor()
    with pytest.raises(RuntimeError, match="ingestion is disabled"):
        executor("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")


@pytest.mark.parametrize(
    "status",
    [
        SchedulerStatus.SOURCE_ERROR,
        SchedulerStatus.PARSE_ERROR,
        SchedulerStatus.VALIDATION_ERROR,
        "ERROR",
    ],
)
def test_scheduler_script_marks_operational_failures_as_process_failure(status):
    assert status in FAILURE_STATUSES
    assert SchedulerStatus.DUPLICATE not in FAILURE_STATUSES
