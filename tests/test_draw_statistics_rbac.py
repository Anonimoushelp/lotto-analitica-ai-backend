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


def _token(user: User) -> str:
    return create_access_token(str(user.id), user.role)


def _seed_lottery(code: str) -> Lottery:
    db = TestingSessionLocal()
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.close()
    return lottery


def _cleanup() -> None:
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


def _seed_draw(lottery_id: int, source: str = "baloto-colombia") -> LotteryDraw:
    db = TestingSessionLocal()
    draw = LotteryDraw(
        lottery_id=lottery_id,
        source=source,
        draw_number="D-001",
        draw_date=date(2026, 9, 15),
        main_numbers=[1, 2, 3, 4, 5],
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    db.close()
    return draw


@pytest.mark.parametrize("role", ["viewer", "service"])
def test_viewer_and_service_cannot_read_draws_or_statistics(role):
    user = _seed_user(f"{role}-read@example.com", role)
    lottery = _seed_lottery(f"{role}-read")
    _seed_draw(lottery.id)
    try:
        headers = _auth(user)
        assert client.get("/api/v1/draws", headers=headers).status_code == 403
        assert client.get(
            "/api/v1/statistics/overview",
            headers=headers,
        ).status_code == 403
    finally:
        _cleanup()


@pytest.mark.parametrize("role", ["viewer", "service", "analyst"])
def test_non_admin_roles_cannot_mutate_draws(role):
    user = _seed_user(f"{role}-mutate@example.com", role)
    lottery = _seed_lottery(f"{role}-mutate")
    draw = _seed_draw(lottery.id)
    try:
        headers = _auth(user)
        payload = {
            "lottery_id": lottery.id,
            "draw_number": "D-002",
            "draw_date": "2026-09-16",
            "main_numbers": [6, 7, 8, 9, 10],
            "source": "baloto-colombia",
        }
        assert client.post("/api/v1/draws", headers=headers, json=payload).status_code == 403
        assert client.put(
            f"/api/v1/draws/{draw.id}",
            headers=headers,
            json={"draw_number": "D-002"},
        ).status_code == 403
        assert client.delete(
            f"/api/v1/draws/{draw.id}",
            headers=headers,
        ).status_code == 403
    finally:
        _cleanup()


def test_admin_and_analyst_can_read_draws_and_statistics_but_only_admin_mutates():
    admin = _seed_user("admin-rbac@example.com", "admin")
    analyst = _seed_user("analyst-rbac@example.com", "analyst")
    lottery = _seed_lottery("RBAC-READ")
    draw = _seed_draw(lottery.id)
    try:
        assert client.get(
            f"/api/v1/draws/{draw.id}",
            headers=_auth(admin),
        ).status_code == 200
        assert client.get(
            f"/api/v1/draws/{draw.id}",
            headers=_auth(analyst),
        ).status_code == 200
        assert client.get(
            f"/api/v1/statistics/overview?lottery_id={lottery.id}&source=baloto-colombia",
            headers=_auth(analyst),
        ).status_code == 200

        update = client.put(
            f"/api/v1/draws/{draw.id}",
            headers=_auth(admin),
            json={"draw_number": "D-ADMIN"},
        )
        assert update.status_code == 200

        denied = client.put(
            f"/api/v1/draws/{draw.id}",
            headers=_auth(analyst),
            json={"draw_number": "D-ANALYST"},
        )
        assert denied.status_code == 403
    finally:
        _cleanup()
