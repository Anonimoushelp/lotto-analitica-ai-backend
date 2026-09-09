from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.membership import Membership
from app.models.plan import Plan
from app.models.tenant import Tenant
from app.models.user import User
from app.services.lottery_draw_service import LotteryDrawService
from app.services.quota_service import QuotaExceededError, QuotaService
from app.services.quota_usage_service import QuotaUsageService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Plan.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
User.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_admin() -> User:
    db = TestingSessionLocal()
    plan = Plan(code="free", name="Free", is_active=True)
    db.add(plan)
    db.flush()
    tenant = Tenant(name="Quota Tenant", slug="quota-tenant", plan_id=plan.id)
    db.add(tenant)
    db.flush()
    user = User(
        email="draw-quota-admin@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role="admin",
            is_active=True,
        )
    )
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
            "draw_date": date(2026, 9, 2),
            "main_numbers": [1, 2, 3, 4, 5],
            "bonus_numbers": None,
            "source": "test",
            "metadata_json": None,
            "created_at": now,
            "updated_at": now,
        },
    )()


client = TestClient(app)


def cleanup():
    db = TestingSessionLocal()
    db.execute(delete(Membership))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.execute(delete(Plan))
    db.commit()
    db.close()


def test_draw_quota_exceeded_returns_429_before_creation(monkeypatch):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        user = seed_admin()
        called = False

        def forbidden_creation(**kwargs):
            nonlocal called
            called = True
            return fake_draw()

        monkeypatch.setattr(QuotaUsageService, "get_current_usage", lambda *args, **kwargs: 100)
        monkeypatch.setattr(
            QuotaService,
            "enforce_if_configured",
            lambda *args, **kwargs: (_ for _ in ()).throw(QuotaExceededError("exceeded")),
        )
        monkeypatch.setattr(LotteryDrawService, "create_draw", forbidden_creation)

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

        assert response.status_code == 429
        assert response.json()["detail"] == "Draw quota exceeded"
        assert called is False
    finally:
        cleanup()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def test_draw_quota_allows_creation_when_within_limit(monkeypatch):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        user = seed_admin()
        enforce_calls = []

        monkeypatch.setattr(QuotaUsageService, "get_current_usage", lambda *args, **kwargs: 2)

        def capture_enforce(*args, **kwargs):
            enforce_calls.append(kwargs)

        monkeypatch.setattr(QuotaService, "enforce_if_configured", capture_enforce)
        monkeypatch.setattr(LotteryDrawService, "create_draw", lambda **kwargs: fake_draw())
        monkeypatch.setattr("app.api.routes.lottery_draws.log_mutation", lambda **kwargs: None)

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
        assert response.json()["draw_number"] == "D-001"
        assert len(enforce_calls) == 1
        assert enforce_calls[0]["tenant_id"] == 1
        assert enforce_calls[0]["quota_code"] == "draws.max"
        assert enforce_calls[0]["current_usage"] == 2
        assert enforce_calls[0]["increment"] == 1
    finally:
        cleanup()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
