from fastapi import APIRouter, Depends, status

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_tenant_admin_or_analyst
from app.schemas.tee import TeeStatusResponse
from app.schemas.tee_operation import TeeOperationRequest, TeeOperationResponse
from app.services.tee_operation_service import execute_tee_attestation
from app.services.tee_service import get_tee_status

router = APIRouter(
    prefix="/api/v1/tee",
    tags=["Trusted Execution Environment"],
)


@router.get("/status", response_model=TeeStatusResponse)
def get_status(
    tenant: TenantContext = Depends(require_tenant_admin_or_analyst),
):
    return get_tee_status()


@router.post(
    "/operations",
    response_model=TeeOperationResponse,
    status_code=status.HTTP_200_OK,
)
def execute_operation(
    request: TeeOperationRequest,
    tenant: TenantContext = Depends(require_tenant_admin_or_analyst),
):
    return execute_tee_attestation(request.nonce)
