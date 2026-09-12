from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.user import User

client = TestClient(app)


class FakeResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeDB:
    bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def __init__(self):
        self.users = [
            User(
                id=1,
                email="admin@example.com",
                password_hash="hash",
                role="admin",
                is_active=True,
                session_version=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ]

    def scalar(self, query):
        text = str(query)
        if "count(users.id)" in text.lower():
            return sum(user.is_active and user.role == "admin" for user in self.users)
        if "users.email" in text.lower():
            return None
        return None

    def scalars(self, query):
        return FakeResult(self.users)

    def get(self, model, user_id):
        return next((user for user in self.users if user.id == user_id), None)

    def add(self, user):
        user.id = max((item.id for item in self.users), default=0) + 1
        now = datetime.now(UTC)
        user.created_at = now
        user.updated_at = now
        self.users.append(user)

    def commit(self):
        return None

    def refresh(self, user):
        return None


def override_user(role="admin", user_id=1):
    return lambda: SimpleNamespace(id=user_id, role=role, is_active=True)


def test_users_requires_admin():
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("analyst")
    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        response = client.get("/api/v1/users")
        assert response.status_code == 403
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_non_admin_cannot_create_users():
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("viewer")
    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        response = client.post(
            "/api/v1/users",
            json={"email": "viewer@example.com", "password": "A-secure-password-123", "role": "viewer"},
        )
        assert response.status_code == 403
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_non_admin_cannot_update_users():
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("analyst")
    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        response = client.patch("/api/v1/users/1", json={"role": "viewer"})
        assert response.status_code == 403
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_admin_can_list_and_create_users():
    db = FakeDB()
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("admin")
    app.dependency_overrides[get_db] = lambda: db
    try:
        listed = client.get("/api/v1/users")
        assert listed.status_code == 200
        assert listed.json()[0]["email"] == "admin@example.com"

        created = client.post(
            "/api/v1/users",
            json={"email": "Analyst@Example.com", "password": "A-secure-password-123", "role": "analyst"},
        )
        assert created.status_code == 201
        assert created.json()["email"] == "analyst@example.com"
        assert created.json()["role"] == "analyst"
        assert "password_hash" not in created.json()
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_admin_can_change_non_admin_role_and_status():
    db = FakeDB()
    db.users.append(
        User(
            id=2,
            email="analyst@example.com",
            password_hash="hash",
            role="analyst",
            is_active=True,
            session_version=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("admin")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.patch(
            "/api/v1/users/2",
            json={"role": "viewer", "is_active": False},
        )
        assert response.status_code == 200
        assert db.users[1].role == "viewer"
        assert db.users[1].is_active is False
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_user_update_cannot_remove_last_active_admin():
    db = FakeDB()
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("admin")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.patch("/api/v1/users/1", json={"is_active": False})
        assert response.status_code == 422
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_user_update_cannot_remove_own_admin_role():
    db = FakeDB()
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("admin", user_id=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.patch("/api/v1/users/1", json={"role": "viewer"})
        assert response.status_code == 422
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_user_creation_rejects_short_password():
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("admin")
    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        response = client.post(
            "/api/v1/users",
            json={"email": "viewer@example.com", "password": "short", "role": "viewer"},
        )
        assert response.status_code == 422
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db


def test_user_password_update_increments_session_version():
    db = FakeDB()
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_current_user] = override_user("admin")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.patch(
            "/api/v1/users/1",
            json={"password": "New-strong-password-123"},
        )
        assert response.status_code == 200
        assert db.users[0].session_version == 1
        assert "password_hash" not in response.json()
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db
