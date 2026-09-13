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


def seed_user(email: str, role: str = "analyst") -> User:
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
        draw_date=datetime(2026, 1, day, tzinfo=UTC),
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


def test_draw_list_filter_isolates_results_by_lottery():
    analyst = seed_user("analyst@example.com")
    first = seed_lottery("ISO-1")
    second = seed_lottery("ISO-2")
    first_draw = seed_draw(first.id, "ISO-001", 1)
    second_draw = seed_draw(second.id, "ISO-001", 2)

    response = client.get(
        "/api/v1/draws",
        params={"lottery_id": first.id},
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [first_draw.id]
    assert body[0]["lottery_id"] == first.id
    assert body[0]["id"] != second_draw.id


def test_draw_list_unknown_lottery_does_not_disclose_other_resources():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("ISO-3")
    draw = seed_draw(lottery.id, "ISO-002", 3)

    response = client.get(
        "/api/v1/draws",
        params={"lottery_id": 2147483647},
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    assert response.json() == []
    assert str(draw.id) not in response.text
    assert "sqlalchemy" not in response.text.lower()
    assert "traceback" not in response.text.lower()


def test_draw_list_rejects_invalid_resource_filter_bounds():
    analyst = seed_user("analyst@example.com")
    headers = auth_header(analyst)

    zero = client.get("/api/v1/draws", params={"lottery_id": 0}, headers=headers)
    negative = client.get("/api/v1/draws", params={"lottery_id": -1}, headers=headers)

    assert zero.status_code == 422
    assert negative.status_code == 422


def test_draw_list_large_resource_filter_does_not_disclose_other_resources():
    analyst = seed_user("analyst@example.com")
    lottery = seed_lottery("ISO-LARGE")
    draw = seed_draw(lottery.id, "ISO-LARGE-001", 4)

    response = client.get(
        "/api/v1/draws",
        params={"lottery_id": 2147483648},
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    assert response.json() == []
    assert str(draw.id) not in response.text


def test_draw_list_limit_is_bounded_and_does_not_cross_filter_boundary():
    analyst = seed_user("analyst@example.com")
    first = seed_lottery("ISO-4")
    second = seed_lottery("ISO-5")
    for index in range(3):
        seed_draw(first.id, f"ISO-4-{index}", 10 + index)
        seed_draw(second.id, f"ISO-5-{index}", 20 + index)

    response = client.get(
        "/api/v1/draws",
        params={"lottery_id": first.id, "limit": 2},
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(item["lottery_id"] == first.id for item in body)


def test_admin_user_resource_enumeration_returns_generic_not_found():
    admin = seed_user("admin@example.com", "admin")
    target = seed_user("target@example.com", "viewer")
    headers = auth_header(admin)

    existing = client.patch(
        f"/api/v1/auth/admin/users/{target.id}",
        headers=headers,
        json={"email": "target-renamed@example.com"},
    )
    missing = client.patch(
        "/api/v1/auth/admin/users/2147483647",
        headers=headers,
        json={"email": "not-found@example.com"},
    )

    assert existing.status_code == 200
    assert missing.status_code == 404
    assert missing.json()["detail"] == "User not found"
    assert "password" not in missing.text.lower()
    assert "session_version" not in missing.text.lower()
    assert "sqlalchemy" not in missing.text.lower()


def test_unauthenticated_enumeration_attempts_do_not_reveal_resource_state():
    lottery = seed_lottery("ISO-6")
    draw = seed_draw(lottery.id, "ISO-6-001", 30)

    for path in (
        f"/api/v1/lotteries/{lottery.id}",
        "/api/v1/lotteries/2147483647",
        f"/api/v1/draws/{draw.id}",
        "/api/v1/draws/2147483647",
    ):
        response = client.get(path)
        assert response.status_code == 401, path
        assert "sqlalchemy" not in response.text.lower()
        assert "traceback" not in response.text.lower()
