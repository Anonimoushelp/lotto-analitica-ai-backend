import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
User.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
AuditEvent.__table__.create(bind=engine)


def override_get_db():
    with Session(engine) as db:
        yield db


client = TestClient(app)


def clean_db() -> None:
    with Session(engine) as db:
        db.execute(delete(AuditEvent))
        db.execute(delete(Membership))
        db.execute(delete(Tenant))
        db.execute(delete(User))
        db.commit()


def seed_user(email: str, role: str) -> tuple[int, int]:
    with Session(engine) as db:
        tenant = Tenant(name=email, slug=email.replace("@", "-").replace(".", "-"))
        user = User(
            email=email,
            password_hash=hash_password("StrongTestPassword123!"),
            role=role,
            is_active=True,
        )
        db.add_all([tenant, user])
        db.flush()
        db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, is_active=True))
        db.commit()
        return user.id, tenant.id


def token_for(user_id: int, role: str) -> str:
    return create_access_token(str(user_id), role)


@pytest.fixture(autouse=True)
def reset_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    clean_db()
    try:
        yield
    finally:
        clean_db()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def add_event(tenant_id: int, actor_user_id: int, details: str = "safe audit detail") -> int:
    with Session(engine) as db:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="membership.update",
            resource_type="membership",
            resource_id="123",
            outcome="success",
            details=details,
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
        db.add(event)
        db.commit()
        return event.id


def test_admin_reads_only_selected_tenant_audit_events():
    actor_id, tenant_id = seed_user("admin@example.com", "admin")
    other_id, other_tenant_id = seed_user("other@example.com", "admin")
    own_event_id = add_event(tenant_id, actor_id)
    other_event_id = add_event(other_tenant_id, other_id)

    response = client.get(
        "/api/v1/audit-events",
        headers={
            "Authorization": f"Bearer {token_for(actor_id, 'admin')}",
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 200
    ids = {event["id"] for event in response.json()}
    assert own_event_id in ids
    assert other_event_id not in ids
    assert all(event["tenant_id"] == tenant_id for event in response.json())


def test_analyst_and_viewer_cannot_read_audit_events():
    for role in ("analyst", "viewer"):
        user_id, tenant_id = seed_user(f"{role}@example.com", role)
        add_event(tenant_id, user_id)
        response = client.get(
            "/api/v1/audit-events",
            headers={
                "Authorization": f"Bearer {token_for(user_id, role)}",
                "X-Tenant-ID": str(tenant_id),
            },
        )
        assert response.status_code == 403
        clean_db()


def test_cross_tenant_audit_event_id_returns_404():
    actor_id, tenant_id = seed_user("selected@example.com", "admin")
    other_id, other_tenant_id = seed_user("other@example.com", "admin")
    other_event_id = add_event(other_tenant_id, other_id)

    response = client.get(
        f"/api/v1/audit-events/{other_event_id}",
        headers={
            "Authorization": f"Bearer {token_for(actor_id, 'admin')}",
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 404


def test_forged_admin_jwt_cannot_read_audit_as_viewer():
    user_id, tenant_id = seed_user("forged@example.com", "viewer")
    add_event(tenant_id, user_id)

    response = client.get(
        "/api/v1/audit-events",
        headers={
            "Authorization": f"Bearer {token_for(user_id, 'admin')}",
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 403


def test_audit_details_do_not_expose_secret_values():
    user_id, tenant_id = seed_user("secrets@example.com", "admin")
    event_id = add_event(tenant_id, user_id, "role=analyst;password_hash=[REDACTED]")

    response = client.get(
        f"/api/v1/audit-events/{event_id}",
        headers={
            "Authorization": f"Bearer {token_for(user_id, 'admin')}",
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "password_hash" not in body["details"]
    assert "StrongTestPassword123!" not in body["details"]
