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
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.services.prediction_service import PredictionService

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


client = TestClient(app)


def seed_user(email: str, role: str) -> tuple[int, int]:
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
    user_id = user.id

    tenant = Tenant(
        name=f"Tenant {email}",
        slug=f"tenant-{user_id}",
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    tenant_id = tenant.id

    db.add(
        Membership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            is_active=True,
        )
    )
    db.commit()
    db.close()
    return user_id, tenant_id


def seed_lottery(tenant_id: int, code: str) -> int:
    db = TestingSessionLocal()
    now = datetime.now(UTC)
    lottery = Lottery(
        tenant_id=tenant_id,
        name=f"Lottery {code}",
        code=code,
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    lottery_id = lottery.id
    db.close()
    return lottery_id


def auth_header(user: tuple[int, int]) -> dict[str, str]:
    user_id, _tenant_id = user
    token = create_access_token(str(user_id), "analyst")
    return {"Authorization": f"Bearer {token}"}


def fake_prediction_response(payload):
    return {
        "summary": {
            "lottery_id": str(payload.lottery_id),
            "lottery_name": "Tenant A Lottery",
            "active_model": "Lotto-Net Gemini AI Core",
            "model_version": "not-configured",
            "overall_confidence": 80.0,
            "top_recommended_numbers": [1],
            "cold_recovery_candidates": [2],
            "recommended_strategy": payload.strategy,
            "last_updated": "2026-01-01T00:00:00+00:00",
        },
        "predictions": [],
        "insights": [],
        "model_status": {
            "model_name": "Lotto-Net Gemini AI Core",
            "version": "not-configured",
            "status": "UNAVAILABLE",
        },
    }


def test_prediction_cross_tenant_lottery_is_denied(monkeypatch):
    tenant_a_user = seed_user("prediction-a@example.com", "analyst")
    tenant_b_user = seed_user("prediction-b@example.com", "analyst")
    lottery_b_id = seed_lottery(tenant_b_user[1], "TENANT-B")
    monkeypatch.setattr(
        "app.api.routes.predictions.ai_rate_limiter.allow", lambda user_id: True
    )

    response = client.post(
        "/api/v1/predictions",
        headers=auth_header(tenant_a_user),
        json={"lottery_id": lottery_b_id, "prediction_count": 1},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Lottery not found"


def test_prediction_tenant_context_is_authoritative(monkeypatch):
    tenant_a_user = seed_user("prediction-context-a@example.com", "analyst")
    tenant_b_user = seed_user("prediction-context-b@example.com", "analyst")
    lottery_a_id = seed_lottery(tenant_a_user[1], "TENANT-A")
    captured = {}

    def fake_generate(db, payload, tenant_id):
        captured["tenant_id"] = tenant_id
        return fake_prediction_response(payload)

    monkeypatch.setattr(PredictionService, "generate", fake_generate)
    monkeypatch.setattr(
        "app.api.routes.predictions.ai_rate_limiter.allow", lambda user_id: True
    )

    response = client.post(
        "/api/v1/predictions",
        headers={
            **auth_header(tenant_a_user),
            "X-Tenant-ID": str(tenant_b_user[1]),
        },
        json={"lottery_id": lottery_a_id, "prediction_count": 1},
    )

    assert response.status_code == 403
    assert captured == {}


def test_prediction_generation_uses_authenticated_tenant(monkeypatch):
    tenant_a_user = seed_user("prediction-valid-a@example.com", "analyst")
    lottery_a_id = seed_lottery(tenant_a_user[1], "TENANT-A")
    captured = {}

    def fake_generate(db, payload, tenant_id):
        captured["tenant_id"] = tenant_id
        captured["lottery_id"] = payload.lottery_id
        return fake_prediction_response(payload)

    monkeypatch.setattr(PredictionService, "generate", fake_generate)
    monkeypatch.setattr(
        "app.api.routes.predictions.ai_rate_limiter.allow", lambda user_id: True
    )

    response = client.post(
        "/api/v1/predictions",
        headers=auth_header(tenant_a_user),
        json={"lottery_id": lottery_a_id, "prediction_count": 1},
    )

    assert response.status_code == 200
    assert captured == {"tenant_id": tenant_a_user[1], "lottery_id": lottery_a_id}


@pytest.mark.parametrize("role", ["viewer", "service"])
def test_prediction_requires_analyst_or_admin(role, monkeypatch):
    user = seed_user(f"prediction-{role}@example.com", role)
    called = False

    def fake_generate(*args, **kwargs):
        nonlocal called
        called = True
        return fake_prediction_response(kwargs["payload"])

    monkeypatch.setattr(PredictionService, "generate", fake_generate)
    monkeypatch.setattr(
        "app.api.routes.predictions.ai_rate_limiter.allow", lambda user_id: True
    )

    response = client.post(
        "/api/v1/predictions",
        headers=auth_header(user),
        json={"lottery_id": 1, "prediction_count": 1},
    )

    assert response.status_code == 403
    assert called is False
