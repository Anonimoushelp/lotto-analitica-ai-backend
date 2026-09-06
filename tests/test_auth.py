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
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
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
        db.execute(delete(Membership))
        db.execute(delete(User))
        db.execute(delete(Tenant))
        db.commit()
        db.close()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def seed_user(email: str, role: str, active: bool = True) -> User:
    db = TestingSessionLocal()
    tenant = Tenant(name="Test Tenant", slug=f"test-{email.replace('@', '-')}")
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=active,
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(
        Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            is_active=active,
        )
    )
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


def test_token_missing_required_claim_is_rejected():
    user = seed_user("missing-claim@example.com", "admin")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "iat": now,
            "type": "access",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Test Lottery", "code": "MISS", "country": "CO"},
    )
    assert response.status_code == 401


def test_db_role_is_authoritative_over_token_role():
    user = seed_user("role-source@example.com", "admin")
    response = client.post(
        "/api/v1/lotteries",
        headers={"Authorization": f"Bearer {token_for(user, role='viewer')}"},
        json={"name": "DB Role Lottery", "code": "DBROLE", "country": "CO"},
    )
    assert response.status_code == 201


def test_login_returns_access_token():
    seed_user("login@example.com", "viewer")
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "StrongTestPassword123!",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_logs_success_without_secrets(caplog):
    user = seed_user("logging-success@example.com", "viewer")
    with caplog.at_level("INFO", logger="app.api.routes.auth"):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": user.email,
                "password": "StrongTestPassword123!",
            },
        )
    assert response.status_code == 200
    assert any("auth.login.success" in record.message for record in caplog.records)
    assert user.email not in caplog.text
    assert "StrongTestPassword123!" not in caplog.text
    assert response.json()["access_token"] not in caplog.text


def test_login_rejects_wrong_password():
    seed_user("wrong-password@example.com", "viewer")
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong-password@example.com",
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_logs_invalid_credentials_without_secrets(caplog):
    seed_user("logging-failure@example.com", "viewer")
    with caplog.at_level("WARNING", logger="app.api.routes.auth"):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "logging-failure@example.com",
                "password": "WrongPassword123!",
            },
        )
    assert response.status_code == 401
    assert any("auth.login.failure" in record.message for record in caplog.records)
    assert "logging-failure@example.com" not in caplog.text
    assert "WrongPassword123!" not in caplog.text


def test_login_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(login_rate_limiter, "allow", lambda email, ip: False)
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "limited@example.com",
            "password": "StrongTestPassword123!",
        },
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_login_rate_limit_logs_event_without_secrets(monkeypatch, caplog):
    monkeypatch.setattr(login_rate_limiter, "allow", lambda email, ip: False)
    with caplog.at_level("WARNING", logger="app.api.routes.auth"):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "logging-rate-limit@example.com",
                "password": "StrongTestPassword123!",
            },
        )
    assert response.status_code == 429
    assert any("auth.login.rate_limited" in record.message for record in caplog.records)
    assert "logging-rate-limit@example.com" not in caplog.text
    assert "StrongTestPassword123!" not in caplog.text


def test_login_fails_closed_when_redis_is_unavailable_in_production(monkeypatch):
    monkeypatch.setattr(
        login_rate_limiter,
        "allow",
        lambda email, ip: (_ for _ in ()).throw(redis.RedisError()),
    )
    original_environment = settings.environment
    settings.environment = "production"
    try:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "unavailable@example.com",
                "password": "StrongTestPassword123!",
            },
        )
        assert response.status_code == 503
    finally:
        settings.environment = original_environment


def test_login_redis_failure_logs_event_without_secrets(monkeypatch, caplog):
    monkeypatch.setattr(
        login_rate_limiter,
        "allow",
        lambda email, ip: (_ for _ in ()).throw(redis.RedisError()),
    )
    original_environment = settings.environment
    settings.environment = "production"
    try:
        with caplog.at_level("ERROR", logger="app.api.routes.auth"):
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "logging-redis-error@example.com",
                    "password": "StrongTestPassword123!",
                },
            )
    finally:
        settings.environment = original_environment
    assert response.status_code == 503
    assert any(
        "auth.login.rate_limiter_unavailable" in record.message
        for record in caplog.records
    )
    assert "logging-redis-error@example.com" not in caplog.text
    assert "StrongTestPassword123!" not in caplog.text


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


def test_initial_registration_always_creates_admin():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = True
    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "bootstrap@example.com",
                "password": "StrongTestPassword123!",
                "role": "viewer",
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == "admin"
        assert "password_hash" not in response.json()
    finally:
        settings.allow_initial_registration = original


def test_initial_registration_emits_safe_audit_event():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = True
    try:
        with patch("app.api.routes.auth.log_mutation") as audit:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "bootstrap-audit@example.com",
                    "password": "StrongTestPassword123!",
                    "role": "viewer",
                },
            )
    finally:
        settings.allow_initial_registration = original

    assert response.status_code == 201
    db = TestingSessionLocal()
    user = db.scalar(select(User).where(User.email == "bootstrap-audit@example.com"))
    db.close()
    assert user is not None
    audit.assert_called_once()
    audit_kwargs = audit.call_args.kwargs
    assert audit_kwargs["action"] == "create"
    assert audit_kwargs["resource"] == "bootstrap_admin"
    assert audit_kwargs["resource_id"] == user.id
    assert audit_kwargs["actor"].id == user.id
    assert audit_kwargs["actor"].role == "admin"
    assert "bootstrap-audit@example.com" not in str(audit.call_args)
    assert "StrongTestPassword123!" not in str(audit.call_args)


def test_initial_registration_does_not_audit_rejected_second_user():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = True
    try:
        first = client.post(
            "/api/v1/auth/register",
            json={
                "email": "first-bootstrap@example.com",
                "password": "StrongTestPassword123!",
            },
        )
        assert first.status_code == 201

        with patch("app.api.routes.auth.log_mutation") as audit:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "second-bootstrap@example.com",
                    "password": "StrongTestPassword123!",
                },
            )
    finally:
        settings.allow_initial_registration = original

    assert response.status_code == 403
    audit.assert_not_called()


def test_registration_rejects_unsupported_role_value():
    original = settings.allow_initial_registration
    settings.allow_initial_registration = True
    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-role@example.com",
                "password": "StrongTestPassword123!",
                "role": "superadmin",
            },
        )
        assert response.status_code == 422
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


def test_production_rejects_initial_registration():
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite://",
            secret_key="x" * 32,
            environment="production",
            allow_initial_registration=True,
            cors_allowed_origins=["https://frontend.example.com"],
        )


def test_production_requires_explicit_cors_origins():
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite://",
            secret_key="x" * 32,
            environment="production",
            allow_initial_registration=False,
        )
