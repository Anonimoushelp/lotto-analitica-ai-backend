from datetime import date, datetime, time

from app.scheduler.draw_schedule import (
    COLOMBIA_TZ,
    ScheduledDraw,
    due_draws,
    expected_window,
)
from app.scheduler.runner import SchedulerRunner


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=COLOMBIA_TZ)


def test_due_draws_uses_colombia_timezone_and_tolerance():
    schedules = (
        ScheduledDraw("TEST", "DIA", expected_time=time(13, 0), tolerance_minutes=30),
    )

    assert [
        (x.lottery_code, x.draw_type)
        for x in due_draws(dt("2026-09-21T13:20:00"), schedules=schedules)
    ] == [("TEST", "DIA")]
    assert due_draws(dt("2026-09-21T13:31:00"), schedules=schedules) == []


def test_due_draws_respects_weekdays():
    schedules = (
        ScheduledDraw(
            "TEST",
            "DIA",
            expected_time=time(13, 0),
            weekdays=frozenset({0}),
        ),
    )
    assert due_draws(dt("2026-09-21T13:10:00"), schedules=schedules)
    assert not due_draws(dt("2026-09-22T13:10:00"), schedules=schedules)


def test_expected_window_is_timezone_aware():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=45)
    start, end = expected_window(schedule, date(2026, 9, 21))
    assert start.tzinfo == COLOMBIA_TZ
    assert (end - start).seconds == 45 * 60


def test_runner_isolates_lottery_and_draw_type():
    calls = []

    def ingest(lottery_code: str, draw_type: str) -> str:
        calls.append((lottery_code, draw_type))
        return "result-not-persisted"

    schedules = (
        ScheduledDraw("TEST", "DIA", time(13, 0)),
        ScheduledDraw("TEST", "DIA", time(13, 5)),
    )
    runner = SchedulerRunner(ingest, schedules=schedules)
    attempts = runner.run_once(dt("2026-09-21T13:10:00"))

    assert calls == [("TEST", "DIA")]
    assert attempts[0].status == "SUCCESS"


def test_runner_records_errors_without_stopping_other_draws():
    calls = []

    def ingest(lottery_code: str, draw_type: str) -> str:
        calls.append((lottery_code, draw_type))
        if draw_type == "DIA":
            raise RuntimeError("source unavailable")
        return "persisted"

    schedules = (
        ScheduledDraw("TEST", "DIA", time(13, 0)),
        ScheduledDraw("TEST", "NOCHE", time(13, 0)),
    )
    runner = SchedulerRunner(ingest, schedules=schedules)
    attempts = runner.run_once(dt("2026-09-21T13:10:00"))

    assert [x.status for x in attempts] == ["ERROR", "SUCCESS"]
    assert calls == [("TEST", "DIA"), ("TEST", "NOCHE")]

def test_due_draws_uses_holiday_specific_time():
    schedule = ScheduledDraw(
        "DORADO",
        "DORADO_NOCHE",
        time(19, 25),
        weekdays=frozenset({6}),
        tolerance_minutes=10,
        holiday_times=(time(19, 28),),
        skip_on_holiday=True,
    )
    holiday = frozenset({date(2026, 9, 20)})

    assert due_draws(
        dt("2026-09-20T19:28:00"),
        schedules=(schedule,),
        holiday_dates=holiday,
    ) == [schedule]
    assert due_draws(
        dt("2026-09-20T19:25:00"),
        schedules=(schedule,),
        holiday_dates=holiday,
    ) == []
