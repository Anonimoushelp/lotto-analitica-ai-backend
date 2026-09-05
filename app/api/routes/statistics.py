from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin_or_analyst
from app.db.session import get_db
from app.schemas.statistics import StatisticalOverviewResponse
from app.services.statistical_service import StatisticalService

router = APIRouter(
    prefix="/api/v1/statistics",
    tags=["Statistics"],
)


@router.get("/overview", response_model=StatisticalOverviewResponse)
def get_statistical_overview(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_analyst),
):
    return StatisticalService.overview(db=db)
