from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User


def fake_draw() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=1,
        lottery_id=1,
        draw_date=datetime.now(UTC).date(),
        winning_numbers=[1, 2, 3, 4, 5],
        created_at=now,
        updated_at=now,
    )


def seed_user(db, role: str) -> User:
    user = User(
        email=f"{role}@example.com",
        password_hash=hash_password("Password123!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def token_for(client: TestClient, role: str) -> str:
    with client.app.dependency_overrides[get_db]() as db:
        user = seed_user(db, role)
        from app.core.security import create_access_token

        return create_access_token(str(user.id), user.role)


def test_draw_mutation_requires_authentication(client: TestClient):
    response = client.post(
        "/api/v1/draws",
        json={"lottery_id": 1, "draw_date": "2026-01-01", "winning_numbers": [1, 2, 3]},
    )
    assert response.status_code == 401


def test_viewer_cannot_mutate_draws(client: TestClient):
    token = token_for(client, "viewer")
    response = client.post(
        "/api/v1/draws",
        headers={"Authorization": f"Bearer {token}"},
        json={"lottery_id": 1, "draw_date": "2026-01-01", "winning_numbers": [1, 2, 3]},
    )
    assert response.status_code == 403


def test_admin_can_create_draw(client: TestClient, monkeypatch):
    token = token_for(client, "admin")
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawService.create_draw",
        lambda self, data: fake_draw(),
    )
    response = client.post(
        "/api/v1/draws",
        headers={"Authorization": f"Bearer {token}"},
        json={"lottery_id": 1, "draw_date": "2026-01-01", "winning_numbers": [1, 2, 3]},
    )
    assert response.status_code == 201


def test_invalid_token_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/draws",
        headers={"Authorization": "Bearer invalid"},
        json={"lottery_id": 1, "draw_date": "2026-01-01", "winning_numbers": [1, 2, 3]},
    )
    assert response.status_code == 401
