from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.core.audit import log_mutation
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserAdminUpdate, UserResponse

router = APIRouter(prefix="/api/v1/admin/users", tags=["Administration"])


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if payload.email is None and payload.password is None and payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes supplied")

    target = db.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target.id == actor.id and (payload.role is not None or payload.is_active is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot change their own role or active status",
        )

    new_role = payload.role if payload.role is not None else target.role
    new_active = payload.is_active if payload.is_active is not None else target.is_active
    if target.role == "admin" and (new_role != "admin" or not new_active):
        active_admins = db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
        )
        if active_admins is not None and active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active administrator must remain",
            )

    changed = False
    if payload.email is not None:
        email = payload.email.strip().lower()
        duplicate = db.scalar(select(User.id).where(User.email == email, User.id != target.id))
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        if email != target.email:
            target.email = email
            changed = True

    if payload.password is not None:
        target.password_hash = hash_password(payload.password)
        changed = True

    if payload.role is not None and payload.role != target.role:
        target.role = payload.role
        changed = True

    if payload.is_active is not None and payload.is_active != target.is_active:
        target.is_active = payload.is_active
        changed = True

    if not changed:
        return target

    target.session_version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User update conflicts with existing data") from None

    db.refresh(target)
    log_mutation(
        action="update_credentials",
        resource="user",
        resource_id=target.id,
        actor=actor,
    )
    return target
