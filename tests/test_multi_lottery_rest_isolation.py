from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
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


@pytest.fixture(autouse=True)
def override_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_user(email: str, role: str) -> User:
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
    db.close()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def _seed_lottery(code: str) -> Lottery:
    db = TestingSessionLocal()
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.close()
    return lottery


def _seed_draw(
    lottery_id: int,
    draw_number: str,
    source: str,
    numbers: list[int],
    day: int,
) -> LotteryDraw:
    db = TestingSessionLocal()
    draw = LotteryDraw(
        lottery_id=lottery_id,
        source=source,
        draw_number=draw_number,
        draw_date=date(2026, 9, day),
        main_numbers=numbers,
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    db.close()
    return draw


def _cleanup() -> None:
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


def test_list_and_statistics_filters_do_not_cross_lottery_or_source():
    user = _seed_user("analyst-isolation@example.com", "analyst")
    lottery_a = _seed_lottery("LOTTERY-A")
    lottery_b = _seed_lottery("LOTTERY-B")
    draw_a = _seed_draw(
        lottery_a.id, "A-001", "baloto-colombia", [1, 2, 3, 4, 5], 15
    )
    draw_b = _seed_draw(
        lottery_b.id, "B-001", "baloto-colombia", [10, 11, 12, 13, 14], 16
    )
    draw_c = _seed_draw(
        lottery_a.id, "A-002", "revancha-colombia", [20, 21, 22, 23, 24], 17
    )

    try:
        headers = _auth(user)

        scoped_lottery = client.get(
            f"/api/v1/draws?lottery_id={lottery_a.id}",
            headers=headers,
        )
        assert scoped_lottery.status_code == 200
        assert {item["id"] for item in scoped_lottery.json()} == {
            draw_a.id,
            draw_c.id,
        }

        scoped_source = client.get(
            f"/api/v1/draws?lottery_id={lottery_a.id}&source=baloto-colombia",
            headers=headers,
        )
        assert scoped_source.status_code == 200
        assert [item["id"] for item in scoped_source.json()] == [draw_a.id]

        statistics_a = client.get(
            f"/api/v1/statistics/overview?lottery_id={lottery_a.id}&source=baloto-colombia",
            headers=headers,
        )
        assert statistics_a.status_code == 200
        assert statistics_a.json()["draws_analyzed"] == 1

        statistics_b = client.get(
            f"/api/v1/statistics/overview?lottery_id={lottery_b.id}&source=baloto-colombia",
            headers=headers,
        )
        assert statistics_b.status_code == 200
        assert statistics_b.json()["draws_analyzed"] == 1

        assert draw_b.id not in {item["id"] for item in scoped_lottery.json()}
        assert draw_c.id not in {item["id"] for item in scoped_source.json()}
    finally:
        _cleanup()


def test_source_filter_is_independent_between_lotteries():
    user = _seed_user("analyst-source@example.com", "analyst")
    lottery_a = _seed_lottery("SOURCE-A")
    lottery_b = _seed_lottery("SOURCE-B")
    draw_a = _seed_draw(
        lottery_a.id, "SHARED-001", "baloto-colombia", [1, 2, 3, 4, 5], 15
    )
    draw_b = _seed_draw(
        lottery_b.id, "SHARED-001", "revancha-colombia", [6, 7, 8, 9, 10], 15
    )

    try:
        headers = _auth(user)
        response = client.get(
            "/api/v1/draws?source=baloto-colombia",
            headers=headers,
        )
        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == {draw_a.id}
        assert draw_b.id not in {item["id"] for item in response.json()}
    finally:
        _cleanup()


def test_draw_id_lookup_is_global_and_returns_only_requested_record():
    user = _seed_user("analyst-id@example.com", "analyst")
    lottery_a = _seed_lottery("ID-A")
    lottery_b = _seed_lottery("ID-B")
    draw_a = _seed_draw(
        lottery_a.id, "ID-001", "baloto-colombia", [1, 2, 3, 4, 5], 15
    )
    draw_b = _seed_draw(
        lottery_b.id, "ID-001", "baloto-colombia", [10, 11, 12, 13, 14], 16
    )

    try:
        headers = _auth(user)
        first = client.get(f"/api/v1/draws/{draw_a.id}", headers=headers)
        second = client.get(f"/api/v1/draws/{draw_b.id}", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == draw_a.id
        assert first.json()["lottery_id"] == lottery_a.id
        assert second.json()["id"] == draw_b.id
        assert second.json()["lottery_id"] == lottery_b.id
    finally:
        _cleanup()
