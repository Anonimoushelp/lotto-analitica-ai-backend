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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def _seed_user(email: str = "admin-payload@example.com") -> User:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def _seed_lottery(code: str = "PAYLOAD-VALIDATION") -> Lottery:
    db = TestingSessionLocal()
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.close()
    return lottery


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def _cleanup() -> None:
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: p.update({"main_numbers": []}),
        lambda p: p.update({"main_numbers": list(range(1, 22))}),
        lambda p: p.update({"main_numbers": [1, 1, 2]}),
        lambda p: p.update({"main_numbers": [0, 2, 3]}),
        lambda p: p.update({"main_numbers": [1, 2, 1001]}),
        lambda p: p.update({"bonus_numbers": list(range(1, 12))}),
        lambda p: p.update({"bonus_numbers": [1, 1]}),
        lambda p: p.update({"bonus_numbers": [0]}),
        lambda p: p.update({"bonus_numbers": [1001]}),
        lambda p: p.update({"bonus_numbers": [3]}),
        lambda p: p.update({"draw_number": "   "}),
        lambda p: p.update({"source": "\t"}),
    ],
)
def test_create_rejects_invalid_number_identifier_and_overlap_payloads(mutator):
    user = _seed_user()
    lottery = _seed_lottery()
    headers = _auth(user)
    payload = {
        "lottery_id": lottery.id,
        "draw_number": "D-001",
        "draw_date": str(date(2026, 9, 18)),
        "main_numbers": [1, 2, 3],
        "bonus_numbers": [4],
        "source": "baloto-colombia",
    }
    try:
        mutator(payload)
        response = client.post("/api/v1/draws", headers=headers, json=payload)
        assert response.status_code == 422
    finally:
        _cleanup()


def test_create_rejects_unknown_fields_and_control_characters():
    user = _seed_user()
    lottery = _seed_lottery()
    headers = _auth(user)
    try:
        payload = {
            "lottery_id": lottery.id,
            "draw_number": "D-001",
            "draw_date": "2026-09-18",
            "main_numbers": [1, 2, 3],
            "source": "baloto-colombia",
            "unexpected": "must-not-be-accepted",
        }
        assert client.post("/api/v1/draws", headers=headers, json=payload).status_code == 422

        payload.pop("unexpected")
        payload["draw_number"] = "D-001\n"
        assert client.post("/api/v1/draws", headers=headers, json=payload).status_code == 422

        payload["draw_number"] = "D-001"
        payload["source"] = "baloto-colombia\n"
        assert client.post("/api/v1/draws", headers=headers, json=payload).status_code == 422
    finally:
        _cleanup()


def test_create_normalizes_outer_whitespace_and_persists_clean_source_and_number():
    user = _seed_user()
    lottery = _seed_lottery()
    headers = _auth(user)
    try:
        response = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery.id,
                "draw_number": "  D-001  ",
                "draw_date": "2026-09-18",
                "main_numbers": [1, 2, 3],
                "source": "  baloto-colombia  ",
            },
        )
        assert response.status_code == 201
        assert response.json()["draw_number"] == "D-001"
        assert response.json()["source"] == "baloto-colombia"
    finally:
        _cleanup()


def test_metadata_rejects_oversized_deep_nonfinite_and_nonprintable_values():
    user = _seed_user()
    lottery = _seed_lottery()
    headers = _auth(user)
    base = {
        "lottery_id": lottery.id,
        "draw_number": "D-001",
        "draw_date": "2026-09-18",
        "main_numbers": [1, 2, 3],
        "source": "baloto-colombia",
    }
    try:
        oversized = {**base, "metadata_json": {"blob": "x" * 600}}
        assert client.post("/api/v1/draws", headers=headers, json=oversized).status_code == 422

        deep = base.copy()
        node = {}
        current = node
        for _ in range(7):
            current["next"] = {}
            current = current["next"]
        deep["metadata_json"] = node
        assert client.post("/api/v1/draws", headers=headers, json=deep).status_code == 422

        control = {**base, "metadata_json": {"note": "bad\nvalue"}}
        assert client.post("/api/v1/draws", headers=headers, json=control).status_code == 422
    finally:
        _cleanup()


def test_update_revalidates_merged_main_and_bonus_numbers():
    user = _seed_user()
    lottery = _seed_lottery()
    headers = _auth(user)
    try:
        create = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery.id,
                "draw_number": "D-001",
                "draw_date": "2026-09-18",
                "main_numbers": [1, 2, 3],
                "bonus_numbers": [4],
                "source": "baloto-colombia",
            },
        )
        assert create.status_code == 201
        draw_id = create.json()["id"]

        overlap_bonus = client.put(
            f"/api/v1/draws/{draw_id}",
            headers=headers,
            json={"bonus_numbers": [2]},
        )
        assert overlap_bonus.status_code == 422

        overlap_main = client.put(
            f"/api/v1/draws/{draw_id}",
            headers=headers,
            json={"main_numbers": [4, 5, 6]},
        )
        assert overlap_main.status_code == 422
    finally:
        _cleanup()


def test_update_rejects_unknown_fields_without_mutation():
    user = _seed_user()
    lottery = _seed_lottery()
    headers = _auth(user)
    try:
        create = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery.id,
                "draw_number": "D-001",
                "draw_date": "2026-09-18",
                "main_numbers": [1, 2, 3],
                "source": "baloto-colombia",
            },
        )
        assert create.status_code == 201
        draw_id = create.json()["id"]

        response = client.put(
            f"/api/v1/draws/{draw_id}",
            headers=headers,
            json={"draw_number": "D-002", "unknown": "reject-me"},
        )
        assert response.status_code == 422

        fetched = client.get(f"/api/v1/draws/{draw_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["draw_number"] == "D-001"
    finally:
        _cleanup()


def test_update_rejects_lottery_change_without_mutation():
    user = _seed_user()
    lottery_a = _seed_lottery("PAYLOAD-A")
    lottery_b = _seed_lottery("PAYLOAD-B")
    headers = _auth(user)
    try:
        create = client.post(
            "/api/v1/draws",
            headers=headers,
            json={
                "lottery_id": lottery_a.id,
                "draw_number": "D-001",
                "draw_date": "2026-09-18",
                "main_numbers": [1, 2, 3],
                "source": "baloto-colombia",
            },
        )
        assert create.status_code == 201
        draw_id = create.json()["id"]

        response = client.put(
            f"/api/v1/draws/{draw_id}",
            headers=headers,
            json={"lottery_id": lottery_b.id},
        )
        assert response.status_code == 409

        fetched = client.get(f"/api/v1/draws/{draw_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["lottery_id"] == lottery_a.id
    finally:
        _cleanup()
