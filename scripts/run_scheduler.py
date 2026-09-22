from __future__ import annotations

import logging
import os
from datetime import datetime

from app.scheduler.draw_schedule import DRAW_SCHEDULES
from app.scheduler.runner import SchedulerRunner

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def ingest_one(lottery_code: str, draw_type: str) -> str:
    # Persistence wiring is intentionally isolated here. The scheduler never
    # chooses a source globally; it passes lottery + draw_type to the ingestion
    # service, which must select the registered primary source and validator.
    raise NotImplementedError(
        f"Ingestion executor not wired yet for {lottery_code}/{draw_type}"
    )


def main() -> int:
    runner = SchedulerRunner(ingest_one, schedules=DRAW_SCHEDULES)
    attempts = runner.run_once(datetime.now().astimezone())
    for attempt in attempts:
        logger.info(
            "scheduler_result lottery=%s draw_type=%s status=%s message=%s",
            attempt.lottery_code,
            attempt.draw_type,
            attempt.status,
            attempt.message,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
