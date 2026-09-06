from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_admin_or_analyst
from app.models.user import User
from app.schemas.tee import TeeStatusResponse
from app.services.tee_service import get_tee_status

router = APIRouter(
    prefix="/api/v1/tee",
    tags=["Trusted Execution Environment"],
)


@router.get("/status", response_model=TeeStatusResponse)
def get_status(
    user: User = Depends(require_admin_or_analyst),
):
    return get_tee_status()
