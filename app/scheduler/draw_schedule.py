from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

COLOMBIA_TZ = ZoneInfo("America/Bogota")


@dataclass(frozen=True)
class ScheduledDraw:
    lottery_code: str
    draw_type: str
    expected_time: time | None
    weekdays: frozenset[int] = frozenset(range(7))
    tolerance_minutes: int = 30
    enabled: bool = True
    holiday_times: tuple[time, ...] = ()
    skip_on_holiday: bool = False
    calendar_only: bool = False


DRAW_SCHEDULES: tuple[ScheduledDraw, ...] = (
    ScheduledDraw("MILOTO", "MILOTO", time(22, 0), frozenset({0, 1, 3, 4}), 45),
    ScheduledDraw("BALOTO", "BALOTO", time(23, 0), frozenset({0, 2, 5}), 45),
    ScheduledDraw("REVANCHA", "REVANCHA", time(23, 0), frozenset({0, 2, 5}), 45),
    ScheduledDraw("ANTIOQUENITA", "ANTIOQUENITA_1", time(10, 0), frozenset({0, 1, 2, 3, 4, 5}), 60),
    ScheduledDraw("ANTIOQUENITA", "ANTIOQUENITA_2", time(16, 0), frozenset(range(7)), 60),
    ScheduledDraw("CHONTICO", "CHONTICO_DIA", time(13, 0), frozenset(range(7)), 60),
    ScheduledDraw("CHONTICO", "CHONTICO_NOCHE", time(19, 0), frozenset({0, 1, 2, 3, 4}), 90),
    ScheduledDraw("CHONTICO", "CHONTICO_NOCHE", time(22, 0), frozenset({5}), 90),
    ScheduledDraw("CHONTICO", "CHONTICO_NOCHE", time(20, 0), frozenset({6}), 90),
    ScheduledDraw("CHONTICO", "CHONTICO_SUPER_NOCHE", time(21, 30), frozenset({3}), 90),
    ScheduledDraw("DORADO", "DORADO_NOCHE", time(22, 5), frozenset({0, 1, 2, 3, 4}), 90),
    ScheduledDraw("DORADO", "DORADO_NOCHE", time(22, 15), frozenset({5}), 90),
    ScheduledDraw("DORADO", "DORADO_NOCHE", time(19, 25), frozenset({6}), 90, holiday_times=(time(19, 28),), skip_on_holiday=True),
    ScheduledDraw("CAFETERITO", "CAFETERITO_TARDE", time(12, 0), frozenset({0, 1, 2, 3, 4, 5}), 90),
    ScheduledDraw("CAFETERITO", "CAFETERITO_NOCHE", time(20, 0), frozenset({0, 1, 2, 3, 4, 5}), 120),
    ScheduledDraw("CAFETERITO", "CAFETERITO_NOCHE", time(21, 0), frozenset({6}), 120),
    ScheduledDraw("CAFETERITO", "CAFETERITO_NOCHE", time(22, 0), frozenset({6}), 120),
    ScheduledDraw("PAISITA", "PAISITA_DIA", time(13, 0), frozenset(range(7)), 60),
    ScheduledDraw("PAISITA", "PAISITA_NOCHE", time(18, 0), frozenset({0, 1, 2, 3, 4, 5}), 90),
    ScheduledDraw("PAISITA", "PAISITA_NOCHE", time(20, 0), frozenset({6}), 90),
)


def due_draws(
    now: datetime,
    *,
    schedules: tuple[ScheduledDraw, ...] = DRAW_SCHEDULES,
    holiday_dates: frozenset[date] = frozenset(),
) -> list[ScheduledDraw]:
    local_now = now.astimezone(COLOMBIA_TZ)
    is_holiday = local_now.date() in holiday_dates
    result: list[ScheduledDraw] = []
    for schedule in schedules:
        if not schedule.enabled or local_now.weekday() not in schedule.weekdays:
            continue
        if is_holiday and schedule.skip_on_holiday and schedule.holiday_times:
            expected_times = schedule.holiday_times
        elif is_holiday and schedule.skip_on_holiday:
            continue
        elif schedule.calendar_only:
            result.append(schedule)
            continue
        else:
            expected_times = (schedule.expected_time,)
        for expected_time in expected_times:
            if expected_time is None:
                continue
            expected = datetime.combine(local_now.date(), expected_time, COLOMBIA_TZ)
            if expected <= local_now <= expected + timedelta(minutes=schedule.tolerance_minutes):
                result.append(schedule)
                break
    return result


def expected_window(
    draw: ScheduledDraw,
    draw_date: date,
    *,
    holiday_dates: frozenset[date] = frozenset(),
) -> tuple[datetime, datetime]:
    if draw.calendar_only:
        return (
            datetime.combine(draw_date, time.min, COLOMBIA_TZ),
            datetime.combine(draw_date, time.max, COLOMBIA_TZ),
        )
    expected_time = (
        draw.holiday_times[0]
        if draw_date in holiday_dates and draw.holiday_times
        else draw.expected_time
    )
    if expected_time is None:
        raise ValueError(f"Schedule {draw.lottery_code}/{draw.draw_type} has no expected time")
    expected = datetime.combine(draw_date, expected_time, COLOMBIA_TZ)
    return expected, expected + timedelta(minutes=draw.tolerance_minutes)
