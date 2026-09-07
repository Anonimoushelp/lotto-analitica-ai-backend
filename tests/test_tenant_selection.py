from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
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
Tenant.__table__.create(bind=engine)
User.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def seed_user(email: str, memberships: list[tuple[str, str, bool]]) -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.flush()
    for slug, role, active in memberships:
        tenant = Tenant(name=slug.title(), slug=slug, is_active=active)
        db.add(tenant)
        db.flush()
        db.add(
            Membership(
                tenant_id=tenant.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
    db.commit()
    db.refresh(user)
    db.close()
    return user


def tenant_ids(user_id: int) -> dict[str, int]:
    db = TestingSessionLocal()
    rows = db.scalars(
        select(Tenant)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == user_id)
    ).all()
    result = {tenant.slug: tenant.id for tenant in rows}
    db.close()
    return result


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


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
    db.execute(delete(Membership))
    db.execute(delete(Lottery))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.commit()
    db.close()


def test_single_active_membership_is_auto_selected(monkeypatch):
    user = seed_user("single@example.com", [("tenant-a", "analyst", True)])
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(LotteryService, "list_lotteries", capture)
    response = client.get("/api/v1/lotteries", headers=auth_header(user))

    assert response.status_code == 200
    assert calls[0]["tenant_id"] == tenant_ids(user.id)["tenant-a"]


def test_multiple_active_memberships_require_explicit_tenant_selection(monkeypatch):
    user = seed_user(
        "multiple@example.com",
        [("tenant-a", "analyst", True), ("tenant-b", "analyst", True)],
    )
    called = False

    def forbidden(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryService, "list_lotteries", forbidden)
    response = client.get("/api/v1/lotteries", headers=auth_header(user))

    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant selection required"
    assert called is False


def test_explicit_membership_selects_requested_tenant(monkeypatch):
    user = seed_user(
        "selected@example.com",
        [("tenant-a", "analyst", True), ("tenant-b", "analyst", True)],
    )
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(LotteryService, "list_lotteries", capture)
    ids = tenant_ids(user.id)
    response = client.get(
        "/api/v1/lotteries",
        headers={**auth_header(user), "X-Tenant-ID": str(ids["tenant-b"])},
    )

    assert response.status_code == 200
    assert calls[0]["tenant_id"] == ids["tenant-b"]


def test_tenant_id_from_another_tenant_is_forbidden(monkeypatch):
    user_a = seed_user("owner-a@example.com", [("tenant-a", "analyst", True)])
    user_b = seed_user("owner-b@example.com", [("tenant-b", "analyst", True)])
    called = False

    def forbidden(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryService, "list_lotteries", forbidden)
    tenant_b_id = tenant_ids(user_b.id)["tenant-b"]
    response = client.get(
        "/api/v1/lotteries",
        headers={**auth_header(user_a), "X-Tenant-ID": str(tenant_b_id)},
    )

    assert response.status_code == 403
    assert called is False


def test_inactive_tenant_is_not_selectable(monkeypatch):
    user = seed_user("inactive-tenant@example.com", [("tenant-a", "analyst", False)])
    called = False

    def forbidden(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryService, "list_lotteries", forbidden)
    tenant_a_id = tenant_ids(user.id)["tenant-a"]
    response = client.get(
        "/api/v1/lotteries",
        headers={**auth_header(user), "X-Tenant-ID": str(tenant_a_id)},
    )

    assert response.status_code == 403
    assert called is False


def test_inactive_membership_is_not_selectable(monkeypatch):
    user = seed_user("inactive-membership@example.com", [("tenant-a", "analyst", True)])
    db = TestingSessionLocal()
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    membership.is_active = False
    db.commit()
    tenant_a_id = membership.tenant_id
    db.close()

    called = False

    def forbidden(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryService, "list_lotteries", forbidden)
    response = client.get(
        "/api/v1/lotteries",
        headers={**auth_header(user), "X-Tenant-ID": str(tenant_a_id)},
    )

    assert response.status_code == 403
    assert called is False


def test_client_tenant_id_cannot_override_authoritative_tenant(monkeypatch):
    user = seed_user("authoritative@example.com", [("tenant-a", "admin", True)])
    calls = []
    now = datetime.now(UTC)

    def capture(**kwargs):
        calls.append(kwargs)
        return Lottery(
            id=1,
            code="LOT-001",
            name="Test Lottery",
            country="CO",
            active=True,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(LotteryService, "create_lottery", capture)
    response = client.post(
        "/api/v1/lotteries",
        headers=auth_header(user),
        json={
            "code": "LOT-001",
            "name": "Test Lottery",
            "country": "CO",
            "active": True,
            "tenant_id": 999999,
        },
    )

    assert response.status_code == 201
    assert calls[0]["tenant_id"] == tenant_ids(user.id)["tenant-a"]
    assert "tenant_id" not in calls[0]["payload"]
