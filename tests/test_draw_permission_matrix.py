from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.user import User
from app.services.lottery_draw_service import LotteryDrawService

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


@pytest.fixture(autouse=True)
def app_db_override():
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.fixture(autouse=True)
def clean_test_data():
    yield
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


client = TestClient(app)


def seed_user(email: str, role: str) -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def fake_draw():
    now = datetime.now(UTC)
    return type(
        "FakeDraw",
        (),
        {
            "id": 1,
            "lottery_id": 1,
            "draw_number": "D-001",
            "draw_date": now.date(),
            "main_numbers": [1, 2, 3, 4, 5],
            "bonus_numbers": None,
            "source": "test",
            "metadata_json": None,
            "created_at": now,
            "updated_at": now,
        },
    )()


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/v1/draws", {"lottery_id": 1, "draw_number": "D-001", "draw_date": "2026-09-02", "main_numbers": [1, 2, 3, 4, 5]}),
        ("put", "/api/v1/draws/1", {"draw_number": "D-002"}),
        ("delete", "/api/v1/draws/1", None),
    ],
)
def test_anonymous_draw_mutations_are_denied_before_service(method, path, json_body, monkeypatch):
    called = False

    def forbidden_service(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    service_method = {"post": "create_draw", "put": "update_draw", "delete": "delete_draw"}[method]
    monkeypatch.setattr(LotteryDrawService, service_method, forbidden_service)

    kwargs = {"json": json_body} if json_body is not None else {}
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert called is False


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/v1/draws", {"lottery_id": 1, "draw_number": "D-001", "draw_date": "2026-09-02", "main_numbers": [1, 2, 3, 4, 5]}),
        ("put", "/api/v1/draws/1", {"draw_number": "D-002"}),
        ("delete", "/api/v1/draws/1", None),
    ],
)
def test_non_admin_roles_cannot_mutate_draws(role, method, path, json_body, monkeypatch):
    user = seed_user(f"{role}-{method}@example.com", role)
    called = False

    def forbidden_service(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    service_method = {"post": "create_draw", "put": "update_draw", "delete": "delete_draw"}[method]
    monkeypatch.setattr(LotteryDrawService, service_method, forbidden_service)

    kwargs = {"json": json_body} if json_body is not None else {}
    response = getattr(client, method)(path, headers=auth_header(user), **kwargs)

    assert response.status_code == 403
    assert called is False


@pytest.mark.parametrize(
    "method,path,json_body,expected_status",
    [
        ("post", "/api/v1/draws", {"lottery_id": 1, "draw_number": "D-001", "draw_date": "2026-09-02", "main_numbers": [1, 2, 3, 4, 5]}, 201),
        ("put", "/api/v1/draws/1", {"draw_number": "D-002"}, 200),
        ("delete", "/api/v1/draws/1", None, 204),
    ],
)
def test_admin_can_mutate_draws(method, path, json_body, expected_status, monkeypatch):
    user = seed_user(f"admin-{method}@example.com", "admin")
    called = False

    def allowed_service(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    service_method = {"post": "create_draw", "put": "update_draw", "delete": "delete_draw"}[method]
    monkeypatch.setattr(LotteryDrawService, service_method, allowed_service)

    kwargs = {"json": json_body} if json_body is not None else {}
    response = getattr(client, method)(path, headers=auth_header(user), **kwargs)

    assert response.status_code == expected_status
    assert called is True


@pytest.mark.parametrize("role", ["admin", "analyst", "viewer", "service"])
@pytest.mark.parametrize("path", ["/api/v1/draws", "/api/v1/draws/1"])
def test_authenticated_read_matrix(role, path, monkeypatch):
    user = seed_user(f"read-{role}@example.com", role)
    if path.endswith("/1"):
        monkeypatch.setattr(LotteryDrawService, "get_draw", lambda **kwargs: fake_draw())
    else:
        monkeypatch.setattr(LotteryDrawService, "list_draws", lambda **kwargs: [])

    response = client.get(path, headers=auth_header(user))

    if role in {"admin", "analyst"}:
        assert response.status_code == 200
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/v1/draws", "/api/v1/draws/1"])
def test_anonymous_draw_reads_require_authentication(path, monkeypatch):
    if path.endswith("/1"):
        monkeypatch.setattr(LotteryDrawService, "get_draw", lambda **kwargs: fake_draw())
    else:
        monkeypatch.setattr(LotteryDrawService, "list_draws", lambda **kwargs: [])

    response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,json_body,expected_action,expected_status",
    [
        ("post", "/api/v1/draws", {"lottery_id": 1, "draw_number": "D-001", "draw_date": "2026-09-02", "main_numbers": [1, 2, 3, 4, 5]}, "create", 201),
        ("put", "/api/v1/draws/1", {"draw_number": "D-002"}, "update", 200),
        ("delete", "/api/v1/draws/1", None, "delete", 204),
    ],
)
def test_admin_mutations_emit_audit_event(method, path, json_body, expected_action, expected_status, monkeypatch):
    user = seed_user(f"audit-admin-{method}@example.com", "admin")
    audit_events = []

    def capture_audit(**kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr("app.api.routes.lottery_draws.log_mutation", capture_audit)
    service_method = {"post": "create_draw", "put": "update_draw", "delete": "delete_draw"}[method]
    monkeypatch.setattr(LotteryDrawService, service_method, lambda **kwargs: fake_draw())

    kwargs = {"json": json_body} if json_body is not None else {}
    response = getattr(client, method)(path, headers=auth_header(user), **kwargs)

    assert response.status_code == expected_status
    assert len(audit_events) == 1
    assert audit_events[0]["action"] == expected_action
    assert audit_events[0]["resource"] == "draw"
    assert audit_events[0]["resource_id"] == 1
    assert audit_events[0]["actor"].id == user.id
    assert audit_events[0]["actor"].role == "admin"


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
def test_rejected_mutation_does_not_emit_audit_event(role, monkeypatch):
    user = seed_user(f"audit-denied-{role}@example.com", role)
    audit_events = []

    def capture_audit(**kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr("app.api.routes.lottery_draws.log_mutation", capture_audit)
    monkeypatch.setattr(LotteryDrawService, "create_draw", lambda **kwargs: fake_draw())

    response = client.post(
        "/api/v1/draws",
        headers=auth_header(user),
        json={
            "lottery_id": 1,
            "draw_number": "D-001",
            "draw_date": "2026-09-02",
            "main_numbers": [1, 2, 3, 4, 5],
        },
    )

    assert response.status_code == 403
    assert audit_events == []


@pytest.mark.parametrize("limit", [0, 501, -1])
def test_draw_list_limit_rejects_out_of_range_before_service(limit, monkeypatch):
    user = seed_user(f"limit-{limit}@example.com", "admin")
    called = False

    def forbidden_service(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", forbidden_service)

    response = client.get(
        f"/api/v1/draws?limit={limit}",
        headers=auth_header(user),
    )

    assert response.status_code == 422
    assert called is False


@pytest.mark.parametrize("limit", [1, 100, 500])
def test_draw_list_limit_accepts_configured_boundaries(limit, monkeypatch):
    user = seed_user(f"limit-ok-{limit}@example.com", "admin")
    calls = []

    def capture_service(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", capture_service)

    response = client.get(
        f"/api/v1/draws?limit={limit}",
        headers=auth_header(user),
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["lottery_id"] is None
    assert calls[0]["limit"] == limit
