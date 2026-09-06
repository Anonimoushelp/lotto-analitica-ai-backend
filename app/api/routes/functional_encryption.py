from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_admin_or_analyst
from app.models.user import User
from app.services.functional_encryption_service import get_functional_encryption_status

router = APIRouter(
    prefix="/api/v1/functional-encryption",
    tags=["Functional Encryption"],
)


@router.get("/status")
def get_status(
    user: User = Depends(require_admin_or_analyst),
):
    return get_functional_encryption_status()
