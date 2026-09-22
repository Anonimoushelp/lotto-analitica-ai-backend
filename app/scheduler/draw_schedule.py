from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

COLOMBIA_TZ = ZoneInfo("America/Bogota")


@dataclass(frozen=True)
class ScheduledDraw:
    lottery_code: str
    draw_type: str
    expected_time: time
    weekdays: frozenset[int] = frozenset(range(7))
    tolerance_minutes: int = 30
    enabled: bool = True


# Times are expected publication/draw windows, not guarantees. Keep the registry
# explicit so source changes can be audited without changing the scheduler.
DRAW_SCHEDULES: tuple[ScheduledDraw, ...] = (
    ScheduledDraw("MILOTO", "MILOTO", time(22, 0), frozenset({0, 1, 3, 4}), 45),
    ScheduledDraw("BALOTO", "BALOTO", time(23, 0), frozenset({0, 2, 5}), 45),
    ScheduledDraw("REVANCHA", "REVANCHA", time(23, 0), frozenset({0, 2, 5}), 45),
    ScheduledDraw("SUPER_ASTRO", "ASTRO_SOL", time(14, 0), frozenset(range(7)), 60),
    ScheduledDraw("SUPER_ASTRO", "ASTRO_LUNA", time(22, 0), frozenset(range(7)), 60),
    ScheduledDraw("ANTIOQUENITA", "ANTIOQUENITA_1", time(10, 0), frozenset({0, 1, 2, 3, 4, 5}), 60),
    ScheduledDraw("ANTIOQUENITA", "ANTIOQUENITA_2", time(16, 0), frozenset(range(7)), 60),
    ScheduledDraw("CHONTICO", "CHONTICO_DIA", time(13, 0), frozenset(range(7)), 60),
    ScheduledDraw("CHONTICO", "CHONTICO_NOCHE", time(19, 0), frozenset({0, 1, 2, 3, 4}), 90),
    ScheduledDraw("CHONTICO", "CHONTICO_NOCHE", time(22, 0), frozenset({5}), 90),
    ScheduledDraw("CHONTICO", "CHONTICO_NOCHE", time(20, 0), frozenset({6}), 90),
    ScheduledDraw("CHONTICO", "CHONTICO_SUPER_NOCHE", time(21, 30), frozenset({3}), 90),
    ScheduledDraw("DORADO", "DORADO_DIA", time(13, 0), frozenset(range(7)), 90),
    ScheduledDraw("DORADO", "DORADO_TARDE", time(18, 0), frozenset(range(7)), 90),
    ScheduledDraw("DORADO", "DORADO_NOCHE", time(22, 0), frozenset(range(7)), 90),
    ScheduledDraw("CAFETERITO", "CAFETERITO_TARDE", time(12, 0), frozenset({0, 1, 2, 3, 4, 5}), 90),
    ScheduledDraw("CAFETERITO", "CAFETERITO_NOCHE", time(20, 0), frozenset({0, 1, 2, 3, 4, 5}), 120),
    ScheduledDraw("PAISITA", "PAISITA_DIA", time(13, 0), frozenset(range(7)), 60),
    ScheduledDraw("PAISITA", "PAISITA_NOCHE", time(18, 0), frozenset({0, 1, 2, 3, 4, 5}), 90),
    ScheduledDraw("PAISITA", "PAISITA_NOCHE", time(20, 0), frozenset({6}), 90),
)


def due_draws(
    now: datetime,
    *,
    schedules: tuple[ScheduledDraw, ...] = DRAW_SCHEDULES,
) -> list[ScheduledDraw]:
    local_now = now.astimezone(COLOMBIA_TZ)
    result: list[ScheduledDraw] = []
    for schedule in schedules:
        if not schedule.enabled or local_now.weekday() not in schedule.weekdays:
            continue
        expected = datetime.combine(local_now.date(), schedule.expected_time, COLOMBIA_TZ)
        lower = expected
        upper = expected + timedelta(minutes=schedule.tolerance_minutes)
        if lower <= local_now <= upper:
            result.append(schedule)
    return result


def expected_window(
    draw: ScheduledDraw,
    draw_date: date,
) -> tuple[datetime, datetime]:
    expected = datetime.combine(draw_date, draw.expected_time, COLOMBIA_TZ)
    return expected, expected + timedelta(minutes=draw.tolerance_minutes)
