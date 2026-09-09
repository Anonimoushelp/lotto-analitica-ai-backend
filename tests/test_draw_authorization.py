from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.user import User
from app.services.lottery_draw_service import LotteryDrawService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Plan.__table__.create(bind=engine)
PlanQuota.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
User.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)


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
    db.execute(delete(Membership))
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.execute(delete(PlanQuota))
    db.execute(delete(Plan))
    db.commit()
    db.close()


def seed_user(email: str, role: str) -> User:
    db = TestingSessionLocal()
    plan = db.scalar(select(Plan).where(Plan.code == "free"))
    if plan is None:
        plan = Plan(code="free", name="Free", is_active=True)
        db.add(plan)
        db.flush()
    tenant = Tenant(name="Test Tenant", slug=f"test-{role}-{email}", plan_id=plan.id)
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=True,
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, is_active=True))
    db.commit()
    db.refresh(user)
    db.close()
    return user


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def fake_draw() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=1,
        lottery_id=1,
        draw_number="D-001",
        draw_date=now.date(),
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=None,
        source="test",
        metadata_json=None,
        created_at=now,
        updated_at=now,
    )


def test_draw_create_requires_authentication(monkeypatch):
    called = False

    def fake_create(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    monkeypatch.setattr(LotteryDrawService, "create_draw", fake_create)
    response = client.post(
        "/api/v1/draws",
        json={
            "lottery_id": 1,
            "draw_number": "D-001",
            "draw_date": "2026-09-02",
            "main_numbers": [1, 2, 3, 4, 5],
        },
    )
    assert response.status_code == 401
    assert called is False


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
def test_draw_create_denies_non_admin_roles(role, monkeypatch):
    user = seed_user(f"{role}@example.com", role)
    called = False

    def fake_create(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    monkeypatch.setattr(LotteryDrawService, "create_draw", fake_create)
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
    assert called is False


def test_draw_create_allows_admin(monkeypatch):
    user = seed_user("admin@example.com", "admin")
    called = False

    def fake_create(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    monkeypatch.setattr(LotteryDrawService, "create_draw", fake_create)
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
    assert response.status_code == 201
    assert called is True


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
def test_draw_update_denies_non_admin_roles(role, monkeypatch):
    user = seed_user(f"{role}@example.com", role)
    called = False

    def fake_update(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    monkeypatch.setattr(LotteryDrawService, "update_draw", fake_update)
    response = client.put(
        "/api/v1/draws/1",
        headers=auth_header(user),
        json={"draw_number": "D-002"},
    )
    assert response.status_code == 403
    assert called is False


def test_draw_update_allows_admin(monkeypatch):
    user = seed_user("admin-update@example.com", "admin")
    called = False

    def fake_update(**kwargs):
        nonlocal called
        called = True
        return fake_draw()

    monkeypatch.setattr(LotteryDrawService, "update_draw", fake_update)
    response = client.put(
        "/api/v1/draws/1",
        headers=auth_header(user),
        json={"draw_number": "D-002"},
    )
    assert response.status_code == 200
    assert called is True


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
def test_draw_delete_denies_non_admin_roles(role, monkeypatch):
    user = seed_user(f"{role}-delete@example.com", role)
    called = False

    def fake_delete(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(LotteryDrawService, "delete_draw", fake_delete)
    response = client.delete(
        "/api/v1/draws/1",
        headers=auth_header(user),
    )
    assert response.status_code == 403
    assert called is False


def test_draw_delete_allows_admin(monkeypatch):
    user = seed_user("admin-delete@example.com", "admin")
    called = False

    def fake_delete(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(LotteryDrawService, "delete_draw", fake_delete)
    response = client.delete(
        "/api/v1/draws/1",
        headers=auth_header(user),
    )
    assert response.status_code == 204
    assert called is True


def test_draw_reads_require_authentication(monkeypatch):
    monkeypatch.setattr(LotteryDrawService, "list_draws", lambda **kwargs: [])
    response = client.get("/api/v1/draws")
    assert response.status_code == 401
