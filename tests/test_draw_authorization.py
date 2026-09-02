from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import get_current_user
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.user import User


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_user(client, email: str, role: str) -> str:
    db = next(app.dependency_overrides[get_db]())
    user = User(
        email=email,
        password_hash=hash_password("test-password"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.core.security import create_access_token

    token = create_access_token(str(user.id), user.role)
    db.close()
    return token


def token_for(client, email: str, role: str) -> str:
    return seed_user(client, email, role)


def fake_draw() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=1,
        lottery_id=1,
        draw_date=date.today(),
        winning_numbers=[1, 2, 3, 4, 5],
        created_at=now,
        updated_at=now,
    )


def test_create_draw_permissions(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.LotteryDrawService.create_draw",
        lambda *args, **kwargs: fake_draw(),
    )
    payload = {
        "lottery_id": 1,
        "draw_date": "2026-09-01",
        "winning_numbers": [1, 2, 3, 4, 5],
    }

    for role, expected in (("admin", 201), ("analyst", 201), ("viewer", 403), ("service", 403)):
        token = token_for(client, f"{role}@example.com", role)
        response = client.post(
            "/api/v1/draws",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == expected


def test_update_draw_permissions(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.LotteryDrawService.update_draw",
        lambda *args, **kwargs: fake_draw(),
    )
    payload = {
        "lottery_id": 1,
        "draw_date": "2026-09-01",
        "winning_numbers": [1, 2, 3, 4, 5],
    }

    for role, expected in (("admin", 200), ("analyst", 200), ("viewer", 403), ("service", 403)):
        token = token_for(client, f"update-{role}@example.com", role)
        response = client.put(
            "/api/v1/draws/1",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == expected


def test_delete_draw_permissions(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.LotteryDrawService.delete_draw",
        lambda *args, **kwargs: None,
    )

    for role, expected in (("admin", 204), ("analyst", 204), ("viewer", 403), ("service", 403)):
        token = token_for(client, f"delete-{role}@example.com", role)
        response = client.delete(
            "/api/v1/draws/1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == expected


def test_draw_reads_remain_public(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.LotteryDrawService.get_draws",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.LotteryDrawService.get_draw",
        lambda *args, **kwargs: None,
    )

    assert client.get("/api/v1/draws").status_code == 200
    assert client.get("/api/v1/draws/1").status_code == 404
