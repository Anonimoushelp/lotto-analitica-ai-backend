from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)
User.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
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


def seed_user(db, email: str, role: str = "admin") -> tuple[User, Tenant]:
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    tenant = Tenant(name=f"Tenant {user.id}", slug=f"tenant-{user.id}", is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, is_active=True))
    db.commit()
    return user, tenant


def seed_draw(db, tenant_id: int, code: str = "DRAW-LOTTERY") -> LotteryDraw:
    now = datetime.now(UTC)
    lottery = Lottery(
        tenant_id=tenant_id,
        name=f"Lottery {code}",
        code=code,
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    draw = LotteryDraw(
        lottery_id=lottery.id,
        draw_number="D-001",
        draw_date=date(2026, 9, 2),
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=[6],
        source="test",
        metadata_json={"fixture": True},
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    return draw


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def cleanup():
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.execute(delete(Membership))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.commit()
    db.close()


def test_cross_tenant_get_draw_returns_404():
    db = TestingSessionLocal()
    user_a, _tenant_a = seed_user(db, "draw-get-a@example.com")
    _user_b, tenant_b = seed_user(db, "draw-get-b@example.com")
    draw_b = seed_draw(db, tenant_b.id)
    headers = auth_header(user_a)
    db.close()

    response = client.get(
        f"/api/v1/draws/{draw_b.id}",
        headers=headers,
    )

    assert response.status_code == 404
    cleanup()


def test_cross_tenant_list_returns_only_current_tenant_draws():
    db = TestingSessionLocal()
    user_a, tenant_a = seed_user(db, "draw-list-a@example.com")
    _user_b, tenant_b = seed_user(db, "draw-list-b@example.com")
    draw_a = seed_draw(db, tenant_a.id, "DRAW-A")
    seed_draw(db, tenant_b.id, "DRAW-B")
    headers = auth_header(user_a)
    draw_a_id = draw_a.id
    db.close()

    response = client.get("/api/v1/draws", headers=headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [draw_a_id]
    cleanup()


def test_cross_tenant_update_returns_404_and_preserves_draw():
    db = TestingSessionLocal()
    user_a, _tenant_a = seed_user(db, "draw-update-a@example.com")
    _user_b, tenant_b = seed_user(db, "draw-update-b@example.com")
    draw_b = seed_draw(db, tenant_b.id)
    draw_id = draw_b.id
    headers = auth_header(user_a)
    db.close()

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=headers,
        json={"draw_number": "ATTACKED"},
    )

    assert response.status_code == 404
    db = TestingSessionLocal()
    persisted = db.get(LotteryDraw, draw_id)
    assert persisted is not None
    assert persisted.draw_number == "D-001"
    db.close()
    cleanup()


def test_cross_tenant_delete_returns_404_and_preserves_draw():
    db = TestingSessionLocal()
    user_a, _tenant_a = seed_user(db, "draw-delete-a@example.com")
    _user_b, tenant_b = seed_user(db, "draw-delete-b@example.com")
    draw_b = seed_draw(db, tenant_b.id)
    draw_id = draw_b.id
    headers = auth_header(user_a)
    db.close()

    response = client.delete(
        f"/api/v1/draws/{draw_id}",
        headers=headers,
    )

    assert response.status_code == 404
    db = TestingSessionLocal()
    assert db.get(LotteryDraw, draw_id) is not None
    db.close()
    cleanup()


def test_create_draw_rejects_lottery_from_another_tenant():
    db = TestingSessionLocal()
    user_a, _tenant_a = seed_user(db, "draw-create-a@example.com")
    _user_b, tenant_b = seed_user(db, "draw-create-b@example.com")
    now = datetime.now(UTC)
    lottery_b = Lottery(
        tenant_id=tenant_b.id,
        name="Tenant B Lottery",
        code="TENANT-B",
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(lottery_b)
    db.commit()
    db.refresh(lottery_b)
    lottery_id = lottery_b.id
    headers = auth_header(user_a)
    db.close()

    response = client.post(
        "/api/v1/draws",
        headers=headers,
        json={
            "lottery_id": lottery_id,
            "draw_number": "D-001",
            "draw_date": "2026-09-03",
            "main_numbers": [1, 2, 3, 4, 5],
            "bonus_numbers": [6],
            "source": "test",
            "metadata_json": {"fixture": True},
        },
    )

    assert response.status_code == 404
    cleanup()


def test_update_draw_rejects_moving_to_lottery_from_another_tenant():
    db = TestingSessionLocal()
    user_a, tenant_a = seed_user(db, "draw-move-a@example.com")
    _user_b, tenant_b = seed_user(db, "draw-move-b@example.com")
    draw_a = seed_draw(db, tenant_a.id, "DRAW-A")
    now = datetime.now(UTC)
    lottery_b = Lottery(
        tenant_id=tenant_b.id,
        name="Tenant B Lottery",
        code="TENANT-B-MOVE",
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(lottery_b)
    db.commit()
    db.refresh(lottery_b)
    lottery_b_id = lottery_b.id
    draw_id = draw_a.id
    headers = auth_header(user_a)
    db.close()

    response = client.put(
        f"/api/v1/draws/{draw_id}",
        headers=headers,
        json={"lottery_id": lottery_b_id},
    )

    assert response.status_code == 404
    db = TestingSessionLocal()
    persisted = db.get(LotteryDraw, draw_id)
    assert persisted is not None
    assert persisted.lottery_id != lottery_b_id
    db.close()
    cleanup()
