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


def seed_user(email: str, role: str = "analyst") -> User:
    db = TestingSessionLocal()
    user = User(email=email, password_hash=hash_password("StrongTestPassword123!"), role=role, is_active=True)
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


def seed_draw(lottery_id: int, number: str, draw_date: datetime) -> LotteryDraw:
    db = TestingSessionLocal()
    draw = LotteryDraw(lottery_id=lottery_id, draw_number=number, draw_date=draw_date, main_numbers=[1, 2, 3, 4, 5], bonus_numbers=[6], source="test")
    db.add(draw)
    db.commit()
    db.refresh(draw)
    db.expunge(draw)
    db.close()
    return draw


def token_for(user: User) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "role": user.role, "session_version": user.session_version, "iat": now, "exp": now + timedelta(minutes=30), "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


def test_draw_list_default_limit_is_bounded():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("PAGE-1")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(105):
        seed_draw(lottery.id, f"PAGE-{index:03d}", start + timedelta(days=index))
    response = client.get("/api/v1/draws", params={"lottery_id": lottery.id}, headers=auth_header(analyst))
    assert response.status_code == 200
    assert len(response.json()) == 100


def test_draw_list_limit_rejects_out_of_range_values():
    analyst = seed_user("analyst@example.com")
    headers = auth_header(analyst)
    zero = client.get("/api/v1/draws", params={"limit": 0}, headers=headers)
    oversized = client.get("/api/v1/draws", params={"limit": 501}, headers=headers)
    assert zero.status_code == 422
    assert oversized.status_code == 422


def test_draw_list_order_is_deterministic_by_draw_date():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("PAGE-2")
    older = seed_draw(lottery.id, "PAGE-A", datetime(2026, 2, 10, tzinfo=UTC))
    newer = seed_draw(lottery.id, "PAGE-B", datetime(2026, 2, 11, tzinfo=UTC))
    response = client.get("/api/v1/draws", params={"lottery_id": lottery.id, "limit": 2}, headers=auth_header(analyst))
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [newer.id, older.id]


def test_draw_list_filter_and_limit_compose_without_cross_resource_leakage():
    analyst = seed_user("analyst@example.com")
    first = seed_lottery("PAGE-3")
    second = seed_lottery("PAGE-4")
    start = datetime(2026, 3, 1, tzinfo=UTC)
    for index in range(4):
        seed_draw(first.id, f"PAGE-3-{index}", start + timedelta(days=index))
        seed_draw(second.id, f"PAGE-4-{index}", start + timedelta(days=10 + index))
    response = client.get("/api/v1/draws", params={"lottery_id": first.id, "limit": 3}, headers=auth_header(analyst))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert {item["lottery_id"] for item in body} == {first.id}
    assert all("PAGE-4" not in item["draw_number"] for item in body)


def test_draw_list_unknown_filter_is_stable_for_large_positive_ids():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("PAGE-5")
    seed_draw(lottery.id, "PAGE-5-1", datetime(2026, 4, 25, tzinfo=UTC))
    response = client.get("/api/v1/draws", params={"lottery_id": 9223372036854775807, "limit": 500}, headers=auth_header(analyst))
    assert response.status_code == 200
    assert response.json() == []
    assert "traceback" not in response.text.lower()
    assert "sqlalchemy" not in response.text.lower()
