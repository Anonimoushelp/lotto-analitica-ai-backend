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
    clear_database()
    try:
        yield
    finally:
        clear_database()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def clear_database():
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


def seed_user(email: str, role: str = "viewer", active: bool = True) -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("Strong" + "Test" + "Password" + "123!"),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def fresh_user(user_id: int) -> User:
    db = TestingSessionLocal()
    user = db.get(User, user_id)
    assert user is not None
    db.expunge(user)
    db.close()
    return user


def token_for(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "session_version": user.session_version,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


def admin_update(admin: User, target: User, payload: dict):
    return client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers=auth_header(admin),
        json=payload,
    )


def test_analyst_has_read_privileges_but_no_mutation_privileges():
    analyst = seed_user("analyst@example.com", role="analyst")
    lottery = Lottery(name="RBAC Lottery", code="RBAC", country="CO")
    db = TestingSessionLocal()
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.close()

    assert client.get("/api/v1/lotteries", headers=auth_header(analyst)).status_code == 200
    assert client.get(
        f"/api/v1/lotteries/{lottery.id}", headers=auth_header(analyst)
    ).status_code == 200
    assert client.get("/api/v1/draws", headers=auth_header(analyst)).status_code == 200
    assert client.get(
        "/api/v1/statistics/overview", headers=auth_header(analyst)
    ).status_code == 200
    assert client.get(
        "/api/v1/predictions/model-status", headers=auth_header(analyst)
    ).status_code == 200
    assert client.post(
        "/api/v1/lotteries",
        headers=auth_header(analyst),
        json={"name": "Denied", "code": "DENIED", "country": "CO"},
    ).status_code == 403


def test_viewer_and_service_roles_are_denied_from_human_analyst_endpoints():
    viewer = seed_user("viewer@example.com", role="viewer")
    service = seed_user("service@example.com", role="service")
    for user in (viewer, service):
        for path in (
            "/api/v1/lotteries",
            "/api/v1/draws",
            "/api/v1/statistics/overview",
            "/api/v1/predictions/model-status",
        ):
            response = client.get(path, headers=auth_header(user))
            assert response.status_code == 403, (user.role, path, response.text)


def test_role_change_to_analyst_grants_only_analyst_scope_and_revokes_old_token():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com", role="viewer")
    old_token = token_for(target)

    response = admin_update(admin, target, {"role": "analyst"})
    assert response.status_code == 200
    assert response.json()["role"] == "analyst"

    refreshed = fresh_user(target.id)
    assert refreshed.role == "analyst"
    assert client.get(
        "/api/v1/statistics/overview", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401
    assert client.get(
        "/api/v1/statistics/overview", headers=auth_header(refreshed)
    ).status_code == 200
    assert client.post(
        "/api/v1/lotteries",
        headers=auth_header(refreshed),
        json={"name": "Denied", "code": "DENIED", "country": "CO"},
    ).status_code == 403


def test_role_demotion_to_viewer_removes_analyst_access_immediately():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com", role="analyst")
    old_token = token_for(target)

    response = admin_update(admin, target, {"role": "viewer"})
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    assert client.get(
        "/api/v1/statistics/overview", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401
    refreshed = fresh_user(target.id)
    assert client.get(
        "/api/v1/statistics/overview", headers=auth_header(refreshed)
    ).status_code == 403


def test_role_change_to_service_cannot_access_human_routes():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com", role="viewer")
    response = admin_update(admin, target, {"role": "service"})
    assert response.status_code == 200
    assert response.json()["role"] == "service"
    refreshed = fresh_user(target.id)
    for path in (
        "/api/v1/lotteries",
        "/api/v1/draws",
        "/api/v1/statistics/overview",
        "/api/v1/predictions/model-status",
    ):
        assert client.get(path, headers=auth_header(refreshed)).status_code == 403


def test_non_admin_roles_cannot_change_any_target_role():
    target = seed_user("target@example.com", role="viewer")
    for role in ("analyst", "viewer", "service"):
        actor = seed_user(f"{role}@example.com", role=role)
        response = admin_update(actor, target, {"role": "admin"})
        assert response.status_code == 403
    db = TestingSessionLocal()
    current = db.get(User, target.id)
    assert current.role == "viewer"
    db.close()


def test_unknown_role_value_fails_closed_at_schema_boundary():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com", role="viewer")
    response = admin_update(admin, target, {"role": "root"})
    assert response.status_code == 422
    db = TestingSessionLocal()
    current = db.get(User, target.id)
    assert current.role == "viewer"
    db.close()


def test_admin_cannot_self_demote_or_self_deactivate():
    admin = seed_user("admin@example.com", role="admin")
    for payload in ({"role": "analyst"}, {"role": "service"}, {"is_active": False}):
        response = client.patch(
            f"/api/v1/auth/admin/users/{admin.id}",
            headers=auth_header(admin),
            json=payload,
        )
        assert response.status_code == 400


def test_last_active_admin_invariant_survives_role_transition(caplog):
    caplog.set_level("INFO", logger="lotto_analitica.audit")
    admin = seed_user("admin@example.com", role="admin")
    second = seed_user("second@example.com", role="admin")

    response = admin_update(admin, second, {"role": "analyst"})
    assert response.status_code == 200
    assert response.json()["role"] == "analyst"

    response = admin_update(admin, admin, {"role": "viewer"})
    assert response.status_code == 400

    db = TestingSessionLocal()
    current_admin = db.get(User, admin.id)
    active_admins = db.query(User).filter(
        User.role == "admin", User.is_active.is_(True)
    ).all()
    assert current_admin.role == "admin"
    assert [user.id for user in active_admins] == [admin.id]
    db.close()
    assert f"actor_user_id={admin.id}" in caplog.text


def test_role_mutation_writes_audit_but_denied_role_mutation_does_not():
    admin = seed_user("admin@example.com", role="admin")
    target = seed_user("target@example.com", role="viewer")
    viewer = seed_user("viewer@example.com", role="viewer")

    response = admin_update(admin, target, {"role": "analyst"})
    assert response.status_code == 200

    db = TestingSessionLocal()
    unchanged = db.get(User, target.id)
    assert unchanged.role == "analyst"
    db.close()

    response = admin_update(viewer, target, {"role": "admin"})
    assert response.status_code == 403
