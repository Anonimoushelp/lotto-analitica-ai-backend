from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin_or_analyst
from app.db.session import get_db
from app.schemas.statistical_analysis import StatisticalAnalysisResponse
from app.schemas.statistics import StatisticalOverviewResponse
from app.services.statistical_service import StatisticalService

router = APIRouter(prefix="/api/v1/statistics", tags=["Statistics"])


@router.get("/overview", response_model=StatisticalOverviewResponse)
def get_statistical_overview(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_analyst),
):
    return StatisticalService.overview(db=db)


@router.get("/analysis", response_model=StatisticalAnalysisResponse)
def get_statistical_analysis(
    lottery_id: int = Query(gt=0),
    source: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_analyst),
):
    return StatisticalService.analysis_response(db=db, lottery_id=lottery_id, source=source)
