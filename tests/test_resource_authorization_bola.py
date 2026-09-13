from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import ALGORITHM, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.user import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)
client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolate_test_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    clear_database()
    try:
        yield
    finally:
        clear_database()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def clear_database():
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
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
    db.expunge(user)
    db.close()
    return user


def seed_lottery() -> Lottery:
    db = TestingSessionLocal()
    lottery = Lottery(code="BOLA-TEST", name="BOLA Test", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.expunge(lottery)
    db.close()
    return lottery


def seed_draw(lottery_id: int) -> LotteryDraw:
    db = TestingSessionLocal()
    draw = LotteryDraw(
        lottery_id=lottery_id,
        draw_number="BOLA-001",
        draw_date=datetime(2026, 1, 1, tzinfo=UTC),
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=[6],
        source="test",
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    db.expunge(draw)
    db.close()
    return draw


def token_for(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "session_version": user.session_version,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


def test_viewer_cannot_access_protected_resource_endpoints():
    viewer = seed_user("viewer@example.com", "viewer")
    lottery = seed_lottery()
    draw = seed_draw(lottery.id)
    headers = auth_header(viewer)

    for path in (
        "/api/v1/lotteries",
        f"/api/v1/lotteries/{lottery.id}",
        "/api/v1/draws",
        f"/api/v1/draws/{draw.id}",
        "/api/v1/statistics/overview",
        "/api/v1/predictions/model-status",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["detail"] == "Insufficient permissions"


def test_analyst_can_read_objects_but_cannot_mutate_them():
    analyst = seed_user("analyst@example.com", "analyst")
    lottery = seed_lottery()
    draw = seed_draw(lottery.id)
    headers = auth_header(analyst)

    assert client.get("/api/v1/lotteries", headers=headers).status_code == 200
    assert client.get(f"/api/v1/lotteries/{lottery.id}", headers=headers).status_code == 200
    assert client.get("/api/v1/draws", headers=headers).status_code == 200
    assert client.get(f"/api/v1/draws/{draw.id}", headers=headers).status_code == 200
    assert client.get("/api/v1/statistics/overview", headers=headers).status_code == 200
    assert client.get("/api/v1/predictions/model-status", headers=headers).status_code == 200

    assert client.post(
        "/api/v1/lotteries",
        headers=headers,
        json={"code": "NEW", "name": "New Lottery", "country": "CO"},
    ).status_code == 403
    assert client.post(
        "/api/v1/draws",
        headers=headers,
        json={
            "lottery_id": lottery.id,
            "draw_number": "BOLA-002",
            "draw_date": "2026-01-02T00:00:00Z",
            "main_numbers": [7, 8, 9],
            "bonus_numbers": [],
            "source": "test",
        },
    ).status_code == 403
    assert client.put(
        f"/api/v1/lotteries/{lottery.id}",
        headers=headers,
        json={"name": "changed"},
    ).status_code == 403
    assert client.put(
        f"/api/v1/draws/{draw.id}",
        headers=headers,
        json={"draw_number": "BOLA-003"},
    ).status_code == 403
    assert client.delete(f"/api/v1/lotteries/{lottery.id}", headers=headers).status_code == 403
    assert client.delete(f"/api/v1/draws/{draw.id}", headers=headers).status_code == 403


def test_service_role_is_denied_human_data_and_admin_routes():
    service = seed_user("service@example.com", "service")
    lottery = seed_lottery()
    draw = seed_draw(lottery.id)
    headers = auth_header(service)

    for path in (
        "/api/v1/lotteries",
        f"/api/v1/lotteries/{lottery.id}",
        "/api/v1/draws",
        f"/api/v1/draws/{draw.id}",
        "/api/v1/statistics/overview",
        "/api/v1/predictions/model-status",
        "/api/v1/auth/admin/users",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path


def test_unknown_resource_ids_do_not_cross_resource_boundaries():
    analyst = seed_user("analyst@example.com", "analyst")
    lottery = seed_lottery()
    draw = seed_draw(lottery.id)
    headers = auth_header(analyst)

    missing_lottery = client.get("/api/v1/lotteries/2147483647", headers=headers)
    missing_draw = client.get("/api/v1/draws/2147483647", headers=headers)
    assert missing_lottery.status_code == 404
    assert missing_draw.status_code == 404
    assert "traceback" not in missing_lottery.text.lower()
    assert "sqlalchemy" not in missing_draw.text.lower()
    assert draw.id != 2147483647


def test_unauthenticated_resource_access_is_401_not_403():
    lottery = seed_lottery()
    draw = seed_draw(lottery.id)
    for path in (
        "/api/v1/lotteries",
        f"/api/v1/lotteries/{lottery.id}",
        "/api/v1/draws",
        f"/api/v1/draws/{draw.id}",
        "/api/v1/statistics/overview",
        "/api/v1/predictions/model-status",
    ):
        response = client.get(path)
        assert response.status_code == 401, path


def test_mutation_denied_by_role_does_not_change_persisted_resource():
    analyst = seed_user("analyst@example.com", "analyst")
    lottery = seed_lottery()
    draw = seed_draw(lottery.id)
    headers = auth_header(analyst)

    response = client.put(
        f"/api/v1/draws/{draw.id}",
        headers=headers,
        json={"draw_number": "SHOULD-NOT-CHANGE"},
    )
    assert response.status_code == 403

    db = TestingSessionLocal()
    current = db.get(LotteryDraw, draw.id)
    assert current.draw_number == "BOLA-001"
    db.close()
