from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw, due_draws


@dataclass(frozen=True)
class IngestionAttempt:
    lottery_code: str
    draw_type: str
    status: str
    message: str


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
            except Exception as exc:
                attempts.append(
                    IngestionAttempt(*key, "ERROR", str(exc))
                )
            else:
                attempts.append(IngestionAttempt(*key, "SUCCESS", message))

        return attempts
