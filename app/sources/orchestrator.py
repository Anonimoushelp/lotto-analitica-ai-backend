from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.services.lottery_draw_service import LotteryDrawService
from app.sources.ingestion import SourceIngestionPipeline

logger = logging.getLogger(__name__)

PipelineFactory = Callable[[], SourceIngestionPipeline]
SessionFactory = Callable[[], Session]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class IngestionJob:
    """Immutable execution policy for one isolated source."""

    key: str
    lottery_code: str
    url: str
    pipeline_factory: PipelineFactory
    interval_seconds: int = 900
    enabled: bool = True
    max_attempts: int = 3
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("job key cannot be empty")
        if not self.lottery_code.strip():
            raise ValueError("lottery_code cannot be empty")
        if self.enabled and not self.url.startswith("https://"):
            raise ValueError("enabled ingestion job URL must use HTTPS")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")


@dataclass(frozen=True)
class IngestionRunResult:
    run_id: str
    job_key: str
    lottery_code: str
    status: str
    attempts: int
    records_seen: int
    records_persisted: int
    error: str | None
    started_at: datetime
    finished_at: datetime


class IngestionOrchestrator:
    """Runs source jobs independently and persists canonical records idempotently."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        sleep: SleepFn = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_factory = session_factory
        self.sleep = sleep
        self.clock = clock

    def run_job(self, job: IngestionJob) -> IngestionRunResult:
        run_id = str(uuid.uuid4())
        started_at = self.clock()
        last_error: Exception | None = None

        if not job.enabled:
            finished_at = self.clock()
            return IngestionRunResult(
                run_id=run_id,
                job_key=job.key,
                lottery_code=job.lottery_code,
                status="disabled",
                attempts=0,
                records_seen=0,
                records_persisted=0,
                error=None,
                started_at=started_at,
                finished_at=finished_at,
            )

        for attempt in range(1, job.max_attempts + 1):
            db = self.session_factory()
            try:
                pipeline = job.pipeline_factory()
                records = pipeline.run(job.url)
                persisted = 0
                for record in records:
                    if record.lottery_code != job.lottery_code:
                        raise ValueError(
                            f"Job {job.key} received record for "
                            f"{record.lottery_code}, expected {job.lottery_code}"
                        )
                    LotteryDrawService.persist_raw_record(db=db, record=record)
                    persisted += 1

                finished_at = self.clock()
                logger.info(
                    "ingestion_completed run_id=%s job=%s source=%s "
                    "attempt=%s records=%s persisted=%s",
                    run_id,
                    job.key,
                    job.lottery_code,
                    attempt,
                    len(records),
                    persisted,
                )
                return IngestionRunResult(
                    run_id=run_id,
                    job_key=job.key,
                    lottery_code=job.lottery_code,
                    status="success",
                    attempts=attempt,
                    records_seen=len(records),
                    records_persisted=persisted,
                    error=None,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            except Exception as exc:
                db.rollback()
                last_error = exc
                logger.exception(
                    "ingestion_attempt_failed run_id=%s job=%s source=%s "
                    "attempt=%s/%s",
                    run_id,
                    job.key,
                    job.lottery_code,
                    attempt,
                    job.max_attempts,
                )
                if attempt < job.max_attempts:
                    self.sleep(job.backoff_seconds * (2 ** (attempt - 1)))
            finally:
                db.close()

        finished_at = self.clock()
        return IngestionRunResult(
            run_id=run_id,
            job_key=job.key,
            lottery_code=job.lottery_code,
            status="failed",
            attempts=job.max_attempts,
            records_seen=0,
            records_persisted=0,
            error=str(last_error) if last_error else "unknown ingestion failure",
            started_at=started_at,
            finished_at=finished_at,
        )
