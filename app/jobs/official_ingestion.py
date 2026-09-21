import logging
import sys

from app.db.session import SessionLocal
from app.services.official_ingestion_runner import OfficialIngestionRunner

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main() -> int:
    db = SessionLocal()
    try:
        runs = OfficialIngestionRunner.run_all(db)
        failed = [run for run in runs if run.status == "failed"]
        skipped = [run for run in runs if run.status == "skipped"]
        if skipped:
            logger.warning("Official ingestion skipped: concurrent run detected")
            return 0
        if failed:
            logger.error(
                "Official ingestion completed with %s failed source(s)",
                len(failed),
            )
            return 1
        logger.info(
            "Official ingestion completed successfully for %s source(s)",
            len(runs),
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
