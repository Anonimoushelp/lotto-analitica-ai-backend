import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, TokenResponse, UserCreate, UserResponse

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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from None
        allowed = True

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": "60"},
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        login_rate_limiter.reset(email, client_ip)
    except redis.RedisError:
        if settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from None

    return TokenResponse(access_token=create_access_token(str(user.id), user.role))


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
    return user


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
