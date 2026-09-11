from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_tenant_manage
from app.db.session import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import TenantResponse, TenantUpdate
from app.services.audit_service import record_audit_event

router = APIRouter(
    prefix="/api/v1/tenant",
    tags=["Tenant"],
)


@router.get("", response_model=TenantResponse)
def get_current_tenant(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant_manage),
):
    current_tenant = db.get(Tenant, tenant.tenant_id)
    if current_tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return current_tenant


@router.patch("", response_model=TenantResponse)
def update_current_tenant(
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant_manage),
):
    if payload.name is None and payload.slug is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one tenant field must be provided",
        )

    current_tenant = db.get(Tenant, tenant.tenant_id)
    if current_tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    previous_name = current_tenant.name
    previous_slug = current_tenant.slug
    if payload.name is not None:
        current_tenant.name = payload.name
    if payload.slug is not None:
        current_tenant.slug = payload.slug

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant slug already exists",
        ) from None

    record_audit_event(
        db,
        tenant_id=tenant.tenant_id,
        actor_user_id=tenant.user_id,
        action="tenant.update",
        resource_type="tenant",
        resource_id=current_tenant.id,
        details=(
            f"name={previous_name}->{current_tenant.name};"
            f"slug={previous_slug}->{current_tenant.slug}"
        ),
    )
    db.commit()
    db.refresh(current_tenant)
    return current_tenant
