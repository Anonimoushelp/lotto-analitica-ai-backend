from __future__ import annotations

import logging
import os
from datetime import datetime

from app.scheduler.catalog_integration import build_catalog_scheduler_bindings, ready_catalog_schedules
from app.scheduler.draw_schedule import DRAW_SCHEDULES
from app.scheduler.runner import SchedulerRunner

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def ingest_one(lottery_code: str, draw_type: str) -> str:
    # Persistence wiring remains intentionally isolated and is not production-ready.
    raise NotImplementedError(f"Ingestion executor not wired yet for {lottery_code}/{draw_type}")


def main() -> int:
    bindings = build_catalog_scheduler_bindings()
    schedules = DRAW_SCHEDULES + ready_catalog_schedules(bindings)
    runner = SchedulerRunner(ingest_one, schedules=schedules)
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
