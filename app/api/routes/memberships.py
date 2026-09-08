from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_memberships_manage
from app.db.session import get_db
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.membership import (
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
)

router = APIRouter(
    prefix="/api/v1/memberships",
    tags=["Memberships"],
)


def _lock_tenant_for_admin_change(db: Session, tenant_id: int) -> None:
    db.scalar(
        select(Tenant.id)
        .where(Tenant.id == tenant_id)
        .with_for_update()
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


@router.patch(
    "/{membership_id}",
    response_model=MembershipResponse,
)
def update_membership(
    membership_id: int,
    payload: MembershipUpdate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_memberships_manage),
):
    if payload.role is None and payload.is_active is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one membership field must be provided",
        )

    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == tenant.tenant_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    becomes_active_admin = (
        membership.role == "admin"
        and membership.is_active
        and (
            (payload.role is not None and payload.role != "admin")
            or payload.is_active is False
        )
    )
    if becomes_active_admin:
        _lock_tenant_for_admin_change(db, tenant.tenant_id)
        active_admins = db.scalar(
            select(func.count(Membership.id)).where(
                Membership.tenant_id == tenant.tenant_id,
                Membership.role == "admin",
                Membership.is_active.is_(True),
            )
        )
        if active_admins == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the last active tenant admin",
            )

    if payload.role is not None:
        membership.role = payload.role
    if payload.is_active is not None:
        membership.is_active = payload.is_active

    db.commit()
    db.refresh(membership)
    return membership


@router.delete(
    "/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_membership(
    membership_id: int,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_memberships_manage),
):
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == tenant.tenant_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    if membership.role == "admin" and membership.is_active:
        _lock_tenant_for_admin_change(db, tenant.tenant_id)
        active_admins = db.scalar(
            select(func.count(Membership.id)).where(
                Membership.tenant_id == tenant.tenant_id,
                Membership.role == "admin",
                Membership.is_active.is_(True),
            )
        )
        if active_admins == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the last active tenant admin",
            )

    membership.is_active = False
    db.commit()
