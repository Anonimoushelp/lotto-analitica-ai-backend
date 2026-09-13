import logging

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, require_admin
from app.core.audit import log_mutation
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    LoginRequest,
    TokenResponse,
    UserAdminUpdate,
    UserCreate,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = payload.email.lower()
    client_ip = request.client.host if request.client else "unknown"

    try:
        allowed = login_rate_limiter.allow(email, client_ip)
    except redis.RedisError:
        if settings.environment == "production":
            logger.error("auth.login.rate_limiter_unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from None
        allowed = True

    if not allowed:
        logger.warning("auth.login.rate_limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": "60"},
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        logger.warning("auth.login.failure reason=invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        login_rate_limiter.reset(email, client_ip)
    except redis.RedisError:
        if settings.environment == "production":
            logger.error("auth.login.rate_limiter_unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from None

    logger.info("auth.login.success user_id=%s", user.id)
    return TokenResponse(
        access_token=create_access_token(
            str(user.id), user.role, session_version=user.session_version
        )
    )


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(831746291)"))

    existing_user = db.scalar(select(User.id).limit(1))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration disabled after bootstrap",
        )
    if not settings.allow_initial_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial registration disabled",
        )

    email = payload.email.lower()
    user = User(email=email, password_hash=hash_password(payload.password), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    log_mutation(
        action="create",
        resource="bootstrap_admin",
        resource_id=user.id,
        actor=user,
    )
    return user


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if all(
        value is None
        for value in (
            payload.email,
            payload.password,
            payload.role,
            payload.is_active,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes supplied",
        )

    target = db.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if target.id == actor.id and (
        payload.role is not None or payload.is_active is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot change their own role or active status",
        )

    new_role = payload.role if payload.role is not None else target.role
    new_active = payload.is_active if payload.is_active is not None else target.is_active
    if target.role == "admin" and (new_role != "admin" or not new_active):
        active_admins = db.scalar(
            select(func.count(User.id)).where(
                User.role == "admin", User.is_active.is_(True)
            )
        )
        if active_admins is not None and active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active administrator must remain",
            )

    changed = False
    if payload.email is not None:
        email = payload.email.strip().lower()
        duplicate = db.scalar(
            select(User.id).where(User.email == email, User.id != target.id)
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User update conflicts with existing data",
        ) from None

    db.refresh(target)
    log_mutation(
        action="update_credentials",
        resource="user",
        resource_id=target.id,
        actor=actor,
    )
    return target
