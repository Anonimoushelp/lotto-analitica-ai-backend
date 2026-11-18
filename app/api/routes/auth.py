import logging

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, require_admin
from app.core.audit import log_mutation
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, TokenResponse, UserCreate, UserResponse

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


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(831746291)"))

    existing_user = db.scalar(select(User.id).limit(1))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration disabled after bootstrap")
    if not settings.allow_initial_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Initial registration disabled")

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


@router.post("/revoke-sessions", status_code=status.HTTP_200_OK)
def revoke_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invalidate every access token issued before this request."""
    user.session_version += 1
    db.commit()
    db.refresh(user)
    log_mutation(
        action="revoke_sessions",
        resource="user",
        resource_id=user.id,
        actor=user,
    )
    return {"detail": "All sessions revoked"}


@router.post(
    "/admin/users/{user_id}/deactivate",
    response_model=UserResponse,
)
def deactivate_user(
    user_id: int,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deactivate an account and invalidate all of its existing sessions."""
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account",
        )

    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if not target.is_active:
        return target

    if target.role == "admin":
        active_admin_ids = db.scalars(
            select(User.id)
            .where(User.role == "admin", User.is_active.is_(True))
            .with_for_update()
        ).all()
        if len(active_admin_ids) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active administrator must remain",
            )

    target.is_active = False
    target.session_version += 1
    db.commit()
    db.refresh(target)
    log_mutation(
        action="deactivate",
        resource="user",
        resource_id=target.id,
        actor=actor,
    )
    return target

