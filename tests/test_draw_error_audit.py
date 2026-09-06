from datetime import date

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.user import User
from app.services.lottery_draw_service import LotteryDrawService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def app_db_override():
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.fixture(autouse=True)
def clean_test_data():
    yield
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(User))
    db.commit()
    db.close()


client = TestClient(app)


def seed_admin() -> User:
    db = TestingSessionLocal()
    user = User(
        email="draw-errors-admin@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


DRAW_CREATE = {
    "lottery_id": 1,
    "draw_number": "D-001",
    "draw_date": date(2026, 9, 2).isoformat(),
    "main_numbers": [1, 2, 3, 4, 5],
}


@pytest.mark.parametrize(
    "method,path,json_body,service_method,detail",
    [
        ("post", "/api/v1/draws", DRAW_CREATE, "create_draw", "Lottery not found"),
        ("put", "/api/v1/draws/1", {"draw_number": "D-002"}, "update_draw", "Lottery draw not found"),
        ("delete", "/api/v1/draws/1", None, "delete_draw", "Lottery draw not found"),
    ],
)
def test_admin_not_found_mutations_do_not_emit_audit(
    method, path, json_body, service_method, detail, monkeypatch
):
    user = seed_admin()
    audit_events = []

    def raise_not_found(**kwargs):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    monkeypatch.setattr(LotteryDrawService, service_method, raise_not_found)
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.log_mutation",
        lambda **kwargs: audit_events.append(kwargs),
    )

    kwargs = {"json": json_body} if json_body is not None else {}
    response = getattr(client, method)(path, headers=auth_header(user), **kwargs)

    assert response.status_code == 404
    assert response.json()["detail"] == detail
    assert audit_events == []


@pytest.mark.parametrize(
    "method,path,json_body,service_method",
    [
        ("post", "/api/v1/draws", DRAW_CREATE, "create_draw"),
        ("put", "/api/v1/draws/1", {"draw_number": "D-002"}, "update_draw"),
    ],
)
def test_admin_conflict_mutations_do_not_emit_audit(
    method, path, json_body, service_method, monkeypatch
):
    user = seed_admin()
    audit_events = []

    def raise_conflict(**kwargs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Draw conflict",
        )

    monkeypatch.setattr(LotteryDrawService, service_method, raise_conflict)
    monkeypatch.setattr(
        "app.api.routes.lottery_draws.log_mutation",
        lambda **kwargs: audit_events.append(kwargs),
    )

    response = getattr(
        client,
        method,
    )(path, headers=auth_header(user), json=json_body)

    assert response.status_code == 409
    assert response.json()["detail"] == "Draw conflict"
    assert audit_events == []
