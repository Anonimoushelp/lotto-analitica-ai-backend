from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.exc import IntegrityError
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
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)
client = TestClient(app)


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_user() -> User:
    db = SessionLocal()
    user = User(
        email="phase345-admin@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def seed_lottery(code: str) -> Lottery:
    db = SessionLocal()
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    db.close()
    return lottery


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def cleanup() -> None:
    db = SessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


import pytest


@pytest.fixture(autouse=True)
def database_override():
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    cleanup()
    yield
    cleanup()
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def create_draw(user: User, lottery_id: int, number: str, draw_date: str, source: str = "baloto-colombia"):
    return client.post(
        "/api/v1/draws",
        headers=auth(user),
        json={
            "lottery_id": lottery_id,
            "draw_number": number,
            "draw_date": draw_date,
            "main_numbers": [1, 2, 3, 4, 5],
            "source": source,
        },
    )


def test_reassignment_preserves_identity_and_provider_provenance():
    user = seed_user()
    lottery_a = seed_lottery("PH345-A")
    lottery_b = seed_lottery("PH345-B")
    created = create_draw(user, lottery_a.id, "D-001", "2026-09-18")
    assert created.status_code == 201
    draw_id = created.json()["id"]

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=auth(user),
        json={"lottery_id": lottery_b.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == draw_id
    assert body["lottery_id"] == lottery_b.id
    assert body["source"] == "baloto-colombia"
    assert body["draw_number"] == "D-001"


def test_reassignment_rejects_target_number_collision_without_mutating_source():
    user = seed_user()
    lottery_a = seed_lottery("PH345-C")
    lottery_b = seed_lottery("PH345-D")
    first = create_draw(user, lottery_a.id, "D-001", "2026-09-18")
    second = create_draw(user, lottery_b.id, "D-001", "2026-09-19")
    assert first.status_code == second.status_code == 201
    draw_id = first.json()["id"]

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=auth(user),
        json={"lottery_id": lottery_b.id},
    )
    assert response.status_code == 409

    fetched = client.get(f"/api/v1/draws/{draw_id}", headers=auth(user))
    assert fetched.status_code == 200
    assert fetched.json()["lottery_id"] == lottery_a.id
    assert fetched.json()["source"] == "baloto-colombia"


def test_reassignment_rejects_target_date_collision_without_mutating_source():
    user = seed_user()
    lottery_a = seed_lottery("PH345-E")
    lottery_b = seed_lottery("PH345-F")
    first = create_draw(user, lottery_a.id, "D-010", "2026-09-18")
    second = create_draw(user, lottery_b.id, "D-011", "2026-09-18")
    assert first.status_code == second.status_code == 201
    draw_id = first.json()["id"]

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=auth(user),
        json={"lottery_id": lottery_b.id},
    )
    assert response.status_code == 409

    fetched = client.get(f"/api/v1/draws/{draw_id}", headers=auth(user))
    assert fetched.status_code == 200
    assert fetched.json()["lottery_id"] == lottery_a.id
    assert fetched.json()["draw_date"] == "2026-09-18"


def test_reassignment_can_move_number_and_date_atomically_to_another_lottery():
    user = seed_user()
    lottery_a = seed_lottery("PH345-G")
    lottery_b = seed_lottery("PH345-H")
    first = create_draw(user, lottery_a.id, "D-020", "2026-09-18")
    assert first.status_code == 201
    draw_id = first.json()["id"]

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=auth(user),
        json={
            "lottery_id": lottery_b.id,
            "draw_number": "D-021",
            "draw_date": "2026-09-19",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == draw_id
    assert body["lottery_id"] == lottery_b.id
    assert body["draw_number"] == "D-021"
    assert body["draw_date"] == "2026-09-19"

    db = SessionLocal()
    rows = db.scalars(select(LotteryDraw).order_by(LotteryDraw.id)).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].lottery_id == lottery_b.id
    assert rows[0].draw_number == "D-021"


def test_reassignment_to_nonexistent_lottery_is_rejected_without_mutation():
    user = seed_user()
    lottery = seed_lottery("PH345-I")
    created = create_draw(user, lottery.id, "D-030", "2026-09-18")
    assert created.status_code == 201
    draw_id = created.json()["id"]

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=auth(user),
        json={"lottery_id": 999999},
    )
    assert response.status_code == 404

    fetched = client.get(f"/api/v1/draws/{draw_id}", headers=auth(user))
    assert fetched.status_code == 200
    assert fetched.json()["lottery_id"] == lottery.id


def test_integrity_error_during_reassignment_rolls_back_all_fields(monkeypatch):
    user = seed_user()
    lottery_a = seed_lottery("PH345-J")
    lottery_b = seed_lottery("PH345-K")
    created = create_draw(user, lottery_a.id, "D-040", "2026-09-18")
    assert created.status_code == 201
    draw_id = created.json()["id"]

    original_commit = SessionLocal.kw["bind"] if False else None
    del original_commit

    from app.services.lottery_draw_service import LotteryDrawService

    real_commit = SessionLocal
    del real_commit
    monkeypatch.setattr(
        "sqlalchemy.orm.Session.commit",
        lambda self: (_ for _ in ()).throw(IntegrityError("forced", {}, Exception("forced"))),
    )

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=auth(user),
        json={
            "lottery_id": lottery_b.id,
            "draw_number": "D-041",
            "draw_date": "2026-09-19",
        },
    )
    assert response.status_code == 409

    db = SessionLocal()
    row = db.scalar(select(LotteryDraw).where(LotteryDraw.id == draw_id))
    db.close()
    assert row.lottery_id == lottery_a.id
    assert row.draw_number == "D-040"
    assert row.draw_date == date(2026, 9, 18)


def test_unique_constraint_failure_isolation_keeps_other_provider_record():
    user = seed_user()
    lottery = seed_lottery("PH345-L")
    baloto = create_draw(user, lottery.id, "D-050", "2026-09-18", "baloto-colombia")
    revancha = create_draw(user, lottery.id, "D-050", "2026-09-18", "revancha-colombia")
    assert baloto.status_code == revancha.status_code == 201

    db = SessionLocal()
    baloto_id = baloto.json()["id"]
    revancha_id = revancha.json()["id"]
    rows = db.scalars(
        select(LotteryDraw).where(LotteryDraw.id.in_([baloto_id, revancha_id]))
    ).all()
    db.close()
    assert {row.source for row in rows} == {"baloto-colombia", "revancha-colombia"}
