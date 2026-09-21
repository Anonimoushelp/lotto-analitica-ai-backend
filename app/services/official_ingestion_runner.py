from datetime import UTC, datetime
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.ingestion_run import IngestionRun
from app.sources.registry import OFFICIAL_SOURCE_ADAPTERS
from app.sources.base import SourceValidationError
from app.services.official_ingestion_service import OfficialIngestionService

logger = logging.getLogger(__name__)

INGESTION_LOCK_KEY = 731942105


class OfficialIngestionRunner:
    """Run registered official-source ingestions with durable audit and DB locking."""

    @staticmethod
    def run_all(db: Session) -> list[IngestionRun]:
        locked = db.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": INGESTION_LOCK_KEY},
        )
        if not locked:
            run = IngestionRun(
                source="all",
                status="skipped",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                error_message="another official ingestion run is already active",
            )
            db.add(run)
            db.commit()
            return [run]

        results: list[IngestionRun] = []
        try:
            for source, adapter_factory in OFFICIAL_SOURCE_ADAPTERS.items():
                results.append(OfficialIngestionRunner.run_source(db, source, adapter_factory))
            return results
        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": INGESTION_LOCK_KEY},
            )
            db.commit()

    @staticmethod
    def run_source(db: Session, source: str, adapter_factory) -> IngestionRun:
        started = datetime.now(UTC)
        run = IngestionRun(source=source, status="running", started_at=started)
        db.add(run)
        db.commit()
        try:
            draw = OfficialIngestionService.ingest(db, adapter_factory())
            run.status = "success"
            run.draw_id = draw.id
            run.finished_at = datetime.now(UTC)
            run.details = {
                "lottery_id": draw.lottery_id,
                "draw_number": draw.draw_number,
                "draw_date": draw.draw_date.isoformat(),
            }
        except (SourceValidationError, Exception) as exc:
            db.rollback()
            run = db.get(IngestionRun, run.id)
            if run is None:
                raise
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_message = str(exc)[:1000]
            logger.exception("Official ingestion failed source=%s run_id=%s", source, run.id)
        db.commit()
        return run
