import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import log_mutation
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_admin_lifecycle_dependencies():
    app.dependency_overrides[get_db] = override_get_db
    yield


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
    return create_access_token(str(user.id), user.role, session_version=user.session_version)


def clear_users():
    db = TestingSessionLocal()
    db.execute(delete(User))
    db.commit()
    db.close()


def test_non_admin_cannot_manage_users():
    viewer = seed_user("viewer-admin-api@example.com", "viewer")
    target = seed_user("target-admin-api@example.com", "viewer")
    response = client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token_for(viewer)}"},
        json={"is_active": False},
    )
    assert response.status_code == 403
    clear_users()


def test_admin_password_change_revokes_previous_token():
    admin = seed_user("admin-password-api@example.com", "admin")
    old_token = token_for(admin)
    response = client.patch(
        f"/api/v1/auth/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {old_token}"},
        json={"password": "NewStrongPassword123!"},
    )
    assert response.status_code == 200

    revoked = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert revoked.status_code == 401
    clear_users()


def test_admin_can_deactivate_other_user_and_session_is_revoked():
    admin = seed_user("admin-deactivate-api@example.com", "admin")
    target = seed_user("target-deactivate-api@example.com", "viewer")
    target_token = token_for(target)
    response = client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    revoked = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert revoked.status_code == 401
    clear_users()


def test_admin_cannot_deactivate_self():
    admin = seed_user("admin-self-api@example.com", "admin")
    response = client.patch(
        f"/api/v1/auth/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={"is_active": False},
    )
    assert response.status_code == 400
    clear_users()


def test_admin_can_manage_multiple_admins_without_removing_last_admin():
    admin = seed_user("admin-last-api@example.com", "admin")
    second_admin = seed_user("admin-second-api@example.com", "admin")
    response = client.patch(
        f"/api/v1/auth/admin/users/{second_admin.id}",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={"role": "viewer"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    clear_users()


def test_admin_user_update_rejects_empty_change_set_and_hides_password_hash():
    admin = seed_user("admin-empty-api@example.com", "admin")
    target = seed_user("target-empty-api@example.com", "viewer")
    response = client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={},
    )
    assert response.status_code == 400

    response = client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={"email": "target-renamed@example.com"},
    )
    assert response.status_code == 200
    assert "password_hash" not in response.json()
    assert response.json()["email"] == "target-renamed@example.com"
    clear_users()


def test_admin_user_update_validates_password_policy_and_unknown_user():
    admin = seed_user("admin-validation-api@example.com", "admin")
    target = seed_user("target-validation-api@example.com", "viewer")
    response = client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={"password": "short"},
    )
    assert response.status_code == 422

    response = client.patch(
        "/api/v1/auth/admin/users/999999",
        headers={"Authorization": f"Bearer {token_for(admin)}"},
        json={"is_active": False},
    )
    assert response.status_code == 404
    clear_users()


def test_log_mutation_records_actor_and_resource(caplog):
    actor = seed_user("audit-log-admin@example.com", "admin")
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"):
        log_mutation(
            action="update_credentials",
            resource="user",
            resource_id=7,
            actor=actor,
        )
    message = caplog.records[-1].getMessage()
    assert "audit.update_credentials" in message
    assert "resource=user" in message
    assert "resource_id=7" in message
    assert f"actor_user_id={actor.id}" in message
    assert "actor_role=admin" in message
    clear_users()


def test_log_mutation_rejects_control_characters_in_actor_role(caplog):
    actor = seed_user("audit-injection@example.com", "admin")
    actor.role = "admin\nforged=true"
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"), pytest.raises(
        ValueError, match="Invalid audit actor role"
    ):
        log_mutation(
            action="update_credentials",
            resource="user",
            resource_id=7,
            actor=actor,
        )
    assert not caplog.records
    clear_users()


def test_log_mutation_does_not_log_password_hash_or_email(caplog):
    actor = seed_user("audit-sensitive@example.com", "admin")
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"):
        log_mutation(
            action="update_credentials",
            resource="user",
            resource_id=7,
            actor=actor,
        )
    message = caplog.records[-1].getMessage()
    assert actor.password_hash not in message
    assert actor.email not in message
    clear_users()


def test_log_mutation_rejects_unsupported_event():
    actor = seed_user("audit-unsupported@example.com", "admin")
    with pytest.raises(ValueError, match="Unsupported audit mutation"):
        log_mutation(
            action="export",
            resource="user",
            resource_id=7,
            actor=actor,
        )
    clear_users()


def test_log_mutation_does_not_emit_unsupported_event(caplog):
    actor = seed_user("audit-noemit@example.com", "admin")
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"), pytest.raises(
        ValueError
    ):
        log_mutation(
            action="delete\nforged=true",
            resource="unknown",
            resource_id=7,
            actor=actor,
        )
    assert not any(record.name == "lotto_analitica.audit" for record in caplog.records)
    clear_users()
