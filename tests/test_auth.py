from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
import redis
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import ALGORITHM, create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_data():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        db = TestingSessionLocal()
        db.execute(delete(Lottery))
        db.execute(delete(User))
        db.commit()
        db.close()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


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


def token_for(user: User, role: str | None = None) -> str:
    return create_access_token(str(user.id), role or user.role)


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
    expired_token = create_access_token(
        str(user.id), user.role, expires_delta=timedelta(seconds=-1)
    )
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"name": "Test Lottery", "code": "EXPIRED", "country": "CO"},
    )
    assert response.status_code == 401


def test_get_lotteries_requires_authentication():
    response = client.get("/api/v1/lotteries")
    assert response.status_code == 401


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
