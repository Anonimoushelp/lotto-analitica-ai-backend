from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_tenant_manage
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.schemas.audit_event import AuditEventResponse

router = APIRouter(
    prefix="/api/v1/audit-events",
    tags=["Audit"],
)


@router.get("", response_model=list[AuditEventResponse])
def list_audit_events(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant_manage),
):
    statement = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant.tenant_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(100)
    )
    return db.scalars(statement).all()


@router.get("/{event_id}", response_model=AuditEventResponse)
def get_audit_event(
    event_id: int,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant_manage),
):
    statement = select(AuditEvent).where(
        AuditEvent.id == event_id,
        AuditEvent.tenant_id == tenant.tenant_id,
    )
    event = db.scalar(statement)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit event not found",
        )
    return event
