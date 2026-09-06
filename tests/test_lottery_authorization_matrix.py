from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.services.lottery_service import LotteryService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
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


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_data():
    yield
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(Membership))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.commit()
    db.close()


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
    tenant = Tenant(name="Test Tenant", slug=f"tenant-{user.id}", is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    db.add(
        Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            is_active=True,
        )
    )
    db.commit()
    db.close()
    return user


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def fake_lottery() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=1,
        name="Test Lottery",
        code="TEST",
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/v1/lotteries", {"name": "Test Lottery", "code": "TEST", "country": "CO"}),
        ("put", "/api/v1/lotteries/1", {"name": "Updated Lottery"}),
        ("delete", "/api/v1/lotteries/1", None),
    ],
)
def test_lottery_mutations_require_authentication(method, path, json_body, monkeypatch):
    called = False

    def fake_mutation(**kwargs):
        nonlocal called
        called = True
        return fake_lottery()

    monkeypatch.setattr(LotteryService, "create_lottery", fake_mutation)
    monkeypatch.setattr(LotteryService, "update_lottery", fake_mutation)
    monkeypatch.setattr(LotteryService, "delete_lottery", fake_mutation)

    response = client.request(method, path, json=json_body)

    assert response.status_code == 401
    assert called is False


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("post", "/api/v1/lotteries", {"name": "Test Lottery", "code": "TEST", "country": "CO"}),
        ("put", "/api/v1/lotteries/1", {"name": "Updated Lottery"}),
        ("delete", "/api/v1/lotteries/1", None),
    ],
)
def test_only_admin_can_mutate_lotteries(role, method, path, json_body, monkeypatch):
    user = seed_user(f"{role}@example.com", role)
    called = False

    def fake_mutation(**kwargs):
        nonlocal called
        called = True
        return fake_lottery()

    monkeypatch.setattr(LotteryService, "create_lottery", fake_mutation)
    monkeypatch.setattr(LotteryService, "update_lottery", fake_mutation)
    monkeypatch.setattr(LotteryService, "delete_lottery", fake_mutation)

    response = client.request(method, path, headers=auth_header(user), json=json_body)

    assert response.status_code == 403
    assert called is False


@pytest.mark.parametrize(
    "method,path,json_body,expected_status",
    [
        ("post", "/api/v1/lotteries", {"name": "Test Lottery", "code": "TEST", "country": "CO"}, 201),
        ("put", "/api/v1/lotteries/1", {"name": "Updated Lottery"}, 200),
    ],
)
def test_admin_can_create_and_update_lotteries(method, path, json_body, expected_status, monkeypatch):
    user = seed_user("admin@example.com", "admin")
    called = False

    def fake_mutation(**kwargs):
        nonlocal called
        called = True
        return fake_lottery()

    monkeypatch.setattr(LotteryService, "create_lottery", fake_mutation)
    monkeypatch.setattr(LotteryService, "update_lottery", fake_mutation)

    response = client.request(method, path, headers=auth_header(user), json=json_body)

    assert response.status_code == expected_status
    assert called is True


def test_admin_can_delete_lottery(monkeypatch):
    user = seed_user("admin-delete@example.com", "admin")
    called = False

    def fake_delete(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(LotteryService, "delete_lottery", fake_delete)

    response = client.delete(
        "/api/v1/lotteries/1",
        headers=auth_header(user),
    )

    assert response.status_code == 204
    assert called is True
