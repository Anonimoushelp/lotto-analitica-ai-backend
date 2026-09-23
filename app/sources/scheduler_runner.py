from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.sources.catalog import build_ingestion_catalog
from app.sources.orchestrator import IngestionOrchestrator
from app.sources.scheduler import PersistentIngestionScheduler

logger = logging.getLogger(__name__)


def main() -> int:
    jobs = build_ingestion_catalog()
    orchestrator = IngestionOrchestrator(session_factory=SessionLocal)
    scheduler = PersistentIngestionScheduler(
        orchestrator=orchestrator,
        jobs=jobs,
        session_factory=SessionLocal,
    )
    from datetime import UTC, datetime

    results = scheduler.run_due(datetime.now(UTC))
    for result in results:
        logger.info(
            "scheduled_ingestion run_id=%s job=%s status=%s attempts=%s "
            "records_seen=%s records_persisted=%s error=%s",
            result.run_id,
            result.job_key,
            result.status,
            result.attempts,
            result.records_seen,
            result.records_persisted,
            result.error,
        )
    failed = sum(result.status == "failed" for result in results)
    logger.info(
        "scheduled_ingestion_cycle jobs=%s executed=%s failed=%s",
        len(jobs),
        len(results),
        failed,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
