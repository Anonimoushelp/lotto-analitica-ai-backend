from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.core.audit import log_mutation
from app.core.config import settings
from app.db.session import get_db
from app.ingestion.loteriaya import LoteriaYaClient
from app.ingestion.service import LotteryIngestionService

router = APIRouter(
    prefix="/api/v1/ingestion",
    tags=["Ingestion"],
)


@router.post("/loteriaya/{lottery_code}", status_code=status.HTTP_200_OK)
def ingest_loteriaya(
    lottery_code: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date cannot be after end_date",
        )

    if not settings.loteriaya_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LoteriaYa ingestion is not configured",
        )

    client = LoteriaYaClient(
        api_key=settings.loteriaya_api_key,
        base_url=settings.loteriaya_base_url,
        timeout=settings.loteriaya_timeout,
    )

    try:
        draws = client.fetch_draw(
            lottery_code=lottery_code,
            start=start_date,
            end=end_date,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Lottery provider request failed",
        ) from exc

    summary = LotteryIngestionService.ingest(db=db, draws=draws)
    log_mutation(
        action="ingest",
        resource="lottery_draws",
        resource_id=None,
        actor=current_user,
    )

    return {
        "provider": "loteriaya",
        "lottery_code": lottery_code,
        "start_date": start_date,
        "end_date": end_date,
        "received": summary.received,
        "inserted": summary.inserted,
        "duplicates": summary.duplicates,
        "rejected": summary.rejected,
    }
