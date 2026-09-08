from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_memberships_manage
from app.db.session import get_db
from app.models.membership import Membership
from app.schemas.membership import MembershipResponse

router = APIRouter(
    prefix="/api/v1/memberships",
    tags=["Memberships"],
)


@router.get("", response_model=list[MembershipResponse])
def list_memberships(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_memberships_manage),
):
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.tenant_id == tenant.tenant_id)
            .order_by(Membership.id)
        ).all()
    )
