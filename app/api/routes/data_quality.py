from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.data_quality import (
    DataQualityAuditResponse,
    DataQualityReconcileRequest,
    DataQualityReconcileResponse,
)
from app.services.data_quality_service import DataQualityService

router = APIRouter(prefix="/api/v1/data-quality", tags=["Data Quality"])


@router.get("/audit", response_model=DataQualityAuditResponse)
def audit(lottery_id: int | None = None, db: Session = Depends(get_db)):
    return DataQualityService.audit(db, lottery_id)


@router.post("/reconcile/{discrepancy_id}", response_model=DataQualityReconcileResponse)
def reconcile(discrepancy_id: str, payload: DataQualityReconcileRequest, db: Session = Depends(get_db)):
    try:
        return DataQualityService.reconcile(db, discrepancy_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
