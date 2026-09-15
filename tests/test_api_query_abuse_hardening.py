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

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


def seed_user(email: str) -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role="analyst",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def seed_lottery(code: str) -> Lottery:
    db = TestingSessionLocal()
    lottery = Lottery(code=code, name=f"Lottery {code}", country="CO")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.expunge(lottery)
    db.close()
    return lottery


def seed_draw(lottery_id: int, number: str, day: int) -> LotteryDraw:
    db = TestingSessionLocal()
    draw = LotteryDraw(
        lottery_id=lottery_id,
        draw_number=number,
        draw_date=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day),
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


def auth_header(user: User) -> dict[str, str]:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "session_version": user.session_version,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "type": "access",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


def test_query_limit_at_maximum_is_bounded_and_does_not_trigger_unbounded_fetch():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("ABUSE-1")
    for index in range(501):
        seed_draw(lottery.id, f"ABUSE-{index:03d}", index)

    response = client.get(
        "/api/v1/draws",
        params={"lottery_id": lottery.id, "limit": 500},
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 500
    assert {item["lottery_id"] for item in body} == {lottery.id}


def test_query_parameters_reject_non_integer_and_repeated_invalid_limit_values():
    analyst = seed_user("analyst@example.com")
    headers = auth_header(analyst)
    for value in ("1.5", "NaN", "1e3", "true"):
        response = client.get(
            "/api/v1/draws", params={"limit": value}, headers=headers
        )
        assert response.status_code == 422

    response = client.get(
        "/api/v1/draws?limit=500&limit=501", headers=headers
    )
    assert response.status_code == 422


def test_filter_and_limit_return_same_deterministic_window_across_repeated_requests():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("ABUSE-2")
    for index in range(12):
        seed_draw(lottery.id, f"ABUSE2-{index:03d}", index)

    params = {"lottery_id": lottery.id, "limit": 7}
    first = client.get("/api/v1/draws", params=params, headers=auth_header(analyst))
    second = client.get("/api/v1/draws", params=params, headers=auth_header(analyst))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_absent_filter_preserves_global_limit_without_cross_resource_expansion():
    analyst = seed_user("analyst@example.com")
    first = seed_lottery("ABUSE-3")
    second = seed_lottery("ABUSE-4")
    for index in range(4):
        seed_draw(first.id, f"ABUSE3-{index}", index)
        seed_draw(second.id, f"ABUSE4-{index}", index + 10)

    response = client.get(
        "/api/v1/draws", params={"limit": 5}, headers=auth_header(analyst)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert {item["lottery_id"] for item in body}.issubset({first.id, second.id})
    assert all(item["lottery_id"] in {first.id, second.id} for item in body)
