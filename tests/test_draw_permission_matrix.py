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


@pytest.mark.parametrize("path", ["/api/v1/draws", "/api/v1/draws/1"])
def test_authenticated_read_roles_can_access_draws(path, monkeypatch):
    user = seed_user("analyst@example.com", "analyst")
    if path.endswith("/1"):
        monkeypatch.setattr(LotteryDrawService, "get_draw", lambda **kwargs: fake_draw())
    else:
        monkeypatch.setattr(LotteryDrawService, "list_draws", lambda **kwargs: [])

    response = client.get(path, headers=auth_header(user))

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/draws", "/api/v1/draws/1"])
def test_anonymous_draw_reads_require_authentication(path, monkeypatch):
    if path.endswith("/1"):
        monkeypatch.setattr(LotteryDrawService, "get_draw", lambda **kwargs: fake_draw())
    else:
        monkeypatch.setattr(LotteryDrawService, "list_draws", lambda **kwargs: [])

    response = client.get(path)

    assert response.status_code == 401
