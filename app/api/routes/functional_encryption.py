from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import require_admin_or_analyst
from app.models.user import User
from app.schemas.functional_encryption import (
    FunctionalEncryptionOperationResponse,
    FunctionalEncryptionRequest,
)
from app.services.functional_encryption_service import (
    execute_functional_encryption,
    get_functional_encryption_status,
)

router = APIRouter(
    prefix="/api/v1/functional-encryption",
    tags=["Functional Encryption"],
)


@router.get("/status")
def get_status(
    user: User = Depends(require_admin_or_analyst),
):
    return get_functional_encryption_status()


@router.post(
    "/operations",
    response_model=FunctionalEncryptionOperationResponse,
)
def execute_operation(
    payload: FunctionalEncryptionRequest,
    user: User = Depends(require_admin_or_analyst),
):
    try:
        result = execute_functional_encryption(
            operation=payload.operation.value,
            payload=payload.payload,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Functional Encryption provider is unavailable",
        ) from exc

    return {
        **get_functional_encryption_status(),
        "operation": payload.operation,
        "result": result,
    }
