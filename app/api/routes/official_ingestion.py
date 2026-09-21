from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.db.session import get_db
from app.services.official_ingestion_service import OfficialIngestionService
from app.sources.base import SourceValidationError
from app.sources.registry import get_official_adapter

router = APIRouter(
    prefix="/api/v1/ingestion",
    tags=["Official Ingestion"],
)


@router.post("/official/{source}", status_code=status.HTTP_201_CREATED)
def ingest_official_source(
    source: str = Path(min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$"),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    try:
        adapter = get_official_adapter(source)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Official source not registered: {source}",
        ) from exc

    try:
        draw = OfficialIngestionService.ingest(db=db, adapter=adapter)
    except SourceValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return {
        "status": "ingested",
        "source": source,
        "draw_id": draw.id,
        "lottery_id": draw.lottery_id,
        "draw_number": draw.draw_number,
        "draw_date": draw.draw_date,
    }
