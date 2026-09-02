from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import LotteryDraw
from app.models.user import User


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def seed_user(email: str, role: str, active: bool = True) -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def token_for(user: User) -> str:
    return create_access_token(str(user.id), user.role)


def test_mutation_requires_authentication():
    response = client.post(
        "/api/v1/lotteries",
        json={"name": "Test Lottery", "code": "TEST", "country": "CO"},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_viewer_cannot_mutate_lotteries():
    user = seed_user("viewer@example.com", "viewer")
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {token_for(user)}"},
        json={"name": "Test Lottery", "code": "TEST", "country": "CO"},
    )
    assert response.status_code == 403


def test_admin_can_create_lottery():
    user = seed_user("admin@example.com", "admin")
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {token_for(user)}"},
        json={"name": "Admin Lottery", "code": "ADMIN", "country": "CO"},
    )
    assert response.status_code == 201
    assert response.json()["code"] == "ADMIN"


def test_invalid_token_is_rejected():
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": "Bearer invalid-token"},
        json={"name": "Test Lottery", "code": "BAD", "country": "CO"},
    )
    assert response.status_code == 401


def test_expired_token_is_rejected():
    user = seed_user("expired@example.com", "admin")
    now = datetime.now(UTC)
    expired_token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "iat": now - timedelta(minutes=60),
            "exp": now - timedelta(minutes=30),
            "type": "access",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"name": "Test Lottery", "code": "EXP", "country": "CO"},
    )
    assert response.status_code == 401


def test_get_lotteries_remains_public():
    response = client.get("/api/v1/lotteries")
    assert response.status_code == 200


def test_me_requires_authentication():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_does_not_expose_password_hash():
    user = seed_user("me@example.com", "viewer")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_for(user)}"},
    )
    assert response.status_code == 200
    assert "password_hash" not in response.json()
    assert response.json()["email"] == user.email


def test_initial_registration_is_disabled_by_default():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = False
    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "bootstrap@example.com",
                "password": "StrongTestPassword123!",
                "role": "viewer",
            },
        )
        assert response.status_code == 403
    finally:
        settings.allow_initial_registration = original


def test_registration_cannot_reopen_after_first_user():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = True
    seed_user("existing@example.com", "admin")
    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "second@example.com",
                "password": "StrongTestPassword123!",
                "role": "viewer",
            },
        )
        assert response.status_code == 403
    finally:
        settings.allow_initial_registration = original
