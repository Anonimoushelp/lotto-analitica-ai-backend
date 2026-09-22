from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw


@dataclass(frozen=True)
class DatedDrawTime:
    draw_date: date
    draw_type: str
    expected_time: time


class DatedSchedule:
    """Calendar-backed schedule for providers with variable dated draw times."""

    def __init__(self, entries: tuple[DatedDrawTime, ...]) -> None:
        self._entries = entries

    def for_date(self, draw_date: date, draw_type: str) -> DatedDrawTime | None:
        matches = [
            entry
            for entry in self._entries
            if entry.draw_date == draw_date and entry.draw_type == draw_type
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(f"Duplicate dated schedule for {draw_type} on {draw_date}")
        return matches[0]

    def as_scheduled_draw(
        self,
        draw_date: date,
        draw_type: str,
        *,
        tolerance_minutes: int = 60,
    ) -> ScheduledDraw | None:
        entry = self.for_date(draw_date, draw_type)
        if entry is None:
            return None
        return ScheduledDraw(
            lottery_code="SUPER_ASTRO",
            draw_type=draw_type,
            expected_time=entry.expected_time,
            weekdays=frozenset({draw_date.weekday()}),
            tolerance_minutes=tolerance_minutes,
        )

    def is_due(
        self,
        now: datetime,
        draw_type: str,
        *,
        tolerance_minutes: int = 60,
    ) -> bool:
        local_now = now.astimezone(COLOMBIA_TZ)
        schedule = self.as_scheduled_draw(
            local_now.date(),
            draw_type,
            tolerance_minutes=tolerance_minutes,
        )
        if schedule is None:
            return False
        expected = datetime.combine(
            local_now.date(), schedule.expected_time, COLOMBIA_TZ
        )
        return expected <= local_now <= expected + timedelta(minutes=tolerance_minutes)
