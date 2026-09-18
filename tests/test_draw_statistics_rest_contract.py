from datetime import date

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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


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


def test_draw_and_statistics_reads_require_authentication():
    assert client.get("/api/v1/draws").status_code == 401
    assert client.get("/api/v1/statistics/overview").status_code == 401


def test_draw_and_statistics_query_contract_rejects_invalid_parameters():
    user = _seed_user("analyst-contract@example.com", "analyst")
    try:
        headers = _auth(user)
        assert client.get("/api/v1/draws?lottery_id=0", headers=headers).status_code == 422
        assert client.get("/api/v1/draws?limit=501", headers=headers).status_code == 422
        assert client.get(
            "/api/v1/statistics/overview?source=",
            headers=headers,
        ).status_code == 422
    finally:
        _cleanup()


def test_draw_rest_lifecycle_and_statistics_contract():
    user = _seed_user("admin-contract@example.com", "admin")
    lottery = _seed_lottery("REST-CONTRACT")
    headers = _auth(user)

    try:
        create = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery.id,
                "draw_number": "D-001",
                "draw_date": str(date(2026, 9, 15)),
                "main_numbers": [1, 2, 3, 4, 5],
                "source": "baloto-colombia",
            },
        )
        assert create.status_code == 201
        draw = create.json()
        assert draw["source"] == "baloto-colombia"

        listing = client.get(
            f"/api/v1/draws?lottery_id={lottery.id}&source=baloto-colombia",
            headers=headers,
        )
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [draw["id"]]

        overview = client.get(
            f"/api/v1/statistics/overview?lottery_id={lottery.id}&source=baloto-colombia",
            headers=headers,
        )
        assert overview.status_code == 200
        assert overview.json() == {
            "module_status": "READY",
            "algorithms_count": 6,
            "draws_analyzed": 1,
        }

        update = client.put(
            f"/api/v1/draws/{draw['id']}",
            headers=headers,
            json={
                "draw_number": "D-002",
                "draw_date": "2026-09-16",
                "main_numbers": [6, 7, 8, 9, 10],
            },
        )
        assert update.status_code == 200
        assert update.json()["draw_number"] == "D-002"

        fetched = client.get(f"/api/v1/draws/{draw['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["main_numbers"] == [6, 7, 8, 9, 10]

        delete_response = client.delete(
            f"/api/v1/draws/{draw['id']}",
            headers=headers,
        )
        assert delete_response.status_code == 204
        assert delete_response.content == b""

        missing = client.get(f"/api/v1/draws/{draw['id']}", headers=headers)
        assert missing.status_code == 404

        standby = client.get(
            f"/api/v1/statistics/overview?lottery_id={lottery.id}&source=baloto-colombia",
            headers=headers,
        )
        assert standby.status_code == 200
        assert standby.json() == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }
    finally:
        _cleanup()


def test_draw_rest_rejects_invalid_payload_and_immutable_source_change():
    user = _seed_user("admin-validation@example.com", "admin")
    lottery = _seed_lottery("REST-VALIDATION")
    headers = _auth(user)

    try:
        invalid = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery.id,
                "draw_number": "D-001",
                "draw_date": "2026-09-15",
                "main_numbers": [1, 1, 2],
                "source": "baloto-colombia",
            },
        )
        assert invalid.status_code == 422

        create = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery.id,
                "draw_number": "D-001",
                "draw_date": "2026-09-15",
                "main_numbers": [1, 2, 3],
                "source": "baloto-colombia",
            },
        )
        assert create.status_code == 201
        draw_id = create.json()["id"]

        source_change = client.put(
            f"/api/v1/draws/{draw_id}",
            headers=headers,
            json={"source": "revancha-colombia"},
        )
        assert source_change.status_code == 409
    finally:
        _cleanup()
