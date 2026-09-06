from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: int
    tenant_id: int
    membership_id: int
    role: str


def get_tenant_context(
    current_user: User,
    db: Session,
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-ID"),
) -> TenantContext:
    query = (
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == current_user.id,
            Membership.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
    )

    if x_tenant_id is not None:
        query = query.where(Membership.tenant_id == x_tenant_id)

    memberships = list(db.scalars(query).all())

    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active tenant membership",
        )

    if x_tenant_id is None and len(memberships) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant selection required",
        )

    membership = memberships[0]
    return TenantContext(
        user_id=current_user.id,
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
        role=membership.role,
    )
