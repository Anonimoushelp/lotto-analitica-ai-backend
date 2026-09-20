from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import ALGORITHM, hash_password
from app.db.session import get_db
from app.main import app
from app.models.user import User

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)
client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolate_test_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    clear_users()
    try:
        yield
    finally:
        clear_users()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def clear_users():
    db = TestingSessionLocal()
    db.execute(delete(User))
    db.commit()
    db.close()


def seed_user(email: str, role: str = "viewer", active: bool = True) -> User:
    db = TestingSessionLocal()
    user = User(email=email, password_hash=hash_password("Strong" + "Test" + "Password" + "123!"), role=role, is_active=active)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def token_for(user: User) -> str:
    payload = {"sub": str(user.id), "role": user.role, "session_version": user.session_version, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=30), "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


def test_admin_update_changes_credentials_and_writes_audit(caplog):
    caplog.set_level("INFO", logger="lotto_analitica.audit")
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com")
    old_version = target.session_version
    response = client.patch(f"/api/v1/auth/admin/users/{target.id}", headers=auth_header(admin), json={"email": "renamed@example.com", "password": "New" + "Strong" + "Password" + "123!"})
    assert response.status_code == 200
    assert response.json()["email"] == "renamed@example.com"
    assert "password_hash" not in response.json()
    db = TestingSessionLocal()
    updated = db.get(User, target.id)
    assert updated.session_version == old_version + 1
    db.close()
    assert "audit.update_credentials" in caplog.text
    assert f"resource_id={target.id}" in caplog.text
    assert f"actor_user_id={admin.id}" in caplog.text


def test_credential_change_revokes_previous_target_token():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com")
    old_token = token_for(target)
    response = client.patch(f"/api/v1/auth/admin/users/{target.id}", headers=auth_header(admin), json={"password": "Another" + "Strong" + "Password" + "123!"})
    assert response.status_code == 200
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Session has been revoked"


def test_admin_deactivation_invalidates_target_session():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com")
    old_token = token_for(target)
    response = client.patch(f"/api/v1/auth/admin/users/{target.id}", headers=auth_header(admin), json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or inactive user"


def test_admin_cannot_change_own_role_or_active_status():
    admin = seed_user("admin@example.com", role="admin")
    for payload in ({"is_active": False}, {"role": "viewer"}):
        response = client.patch(f"/api/v1/auth/admin/users/{admin.id}", headers=auth_header(admin), json=payload)
        assert response.status_code == 400
        assert response.json()["detail"] == "Administrators cannot change their own role or active status"


def test_admin_lifecycle_can_reduce_multiple_admins_to_one_but_not_zero():
    admin = seed_user("admin@example.com", role="admin")
    second = seed_user("second@example.com", role="admin")
    third = seed_user("third@example.com", role="admin")
    assert client.patch(f"/api/v1/auth/admin/users/{second.id}", headers=auth_header(admin), json={"is_active": False}).status_code == 200
    assert client.patch(f"/api/v1/auth/admin/users/{third.id}", headers=auth_header(admin), json={"is_active": False}).status_code == 200
    db = TestingSessionLocal()
    active_admins = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).all()
    assert [user.id for user in active_admins] == [admin.id]
    db.close()
    for payload in ({"is_active": False}, {"role": "viewer"}):
        response = client.patch(f"/api/v1/auth/admin/users/{admin.id}", headers=auth_header(admin), json=payload)
        assert response.status_code == 400


def test_duplicate_email_does_not_mutate_target():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com")
    seed_user("existing@example.com")
    response = client.patch(f"/api/v1/auth/admin/users/{target.id}", headers=auth_header(admin), json={"email": "EXISTING@example.com"})
    assert response.status_code == 409
    db = TestingSessionLocal()
    current = db.get(User, target.id)
    assert current.email == "target@example.com"
    db.close()


def test_admin_user_update_requires_change_and_non_admin_is_denied():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com")
    response = client.patch(f"/api/v1/auth/admin/users/{target.id}", headers=auth_header(admin), json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "No changes supplied"
    viewer = seed_user("viewer@example.com", role="viewer")
    response = client.patch(f"/api/v1/auth/admin/users/{target.id}", headers=auth_header(viewer), json={"is_active": False})
    assert response.status_code == 403
