from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_memberships_manage
from app.db.session import get_db
from app.models.membership import Membership
from app.models.user import User
from app.schemas.membership import MembershipCreate, MembershipResponse

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


@router.post(
    "",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_membership(
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_memberships_manage),
):
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create membership for inactive user",
        )

    existing = db.scalar(
        select(Membership.id).where(
            Membership.tenant_id == tenant.tenant_id,
            Membership.user_id == payload.user_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Membership already exists",
        )

    membership = Membership(
        tenant_id=tenant.tenant_id,
        user_id=payload.user_id,
        role=payload.role,
        is_active=True,
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Membership already exists",
        ) from None

    db.refresh(membership)
    return membership
