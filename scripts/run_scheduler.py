from __future__ import annotations

import logging
import os
from datetime import datetime

from app.scheduler.catalog_integration import (
    build_catalog_scheduler_bindings,
    ready_catalog_schedules,
)
from app.scheduler.draw_schedule import DRAW_SCHEDULES
from app.scheduler.executor import build_controlled_executor
from app.scheduler.runner import SchedulerRunner

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def build_ingest_executor():
    enabled = os.getenv("SCHEDULER_ENABLE_INGESTION", "").strip().lower()
    if enabled not in {"1", "true", "yes"}:
        def disabled_ingest(lottery_code: str, draw_type: str) -> str:
            raise RuntimeError(
                "Scheduler ingestion is disabled; set "
                "SCHEDULER_ENABLE_INGESTION=true for controlled execution"
            )

        return disabled_ingest
    return build_controlled_executor()


def main() -> int:
    bindings = build_catalog_scheduler_bindings()
    schedules = DRAW_SCHEDULES + ready_catalog_schedules(bindings)
    runner = SchedulerRunner(build_ingest_executor(), schedules=schedules)
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
