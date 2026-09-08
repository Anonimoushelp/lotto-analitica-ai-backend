import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
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


def override_get_db():
    with Session(engine) as db:
        yield db


client = TestClient(app)


def clean_db() -> None:
    with Session(engine) as db:
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
        membership = Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            is_active=True,
        )
        db.add(membership)
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


@pytest.mark.parametrize("role", ["analyst", "viewer"])
def test_non_admin_cannot_manage_memberships_or_tenant(role: str):
    user_id, tenant_id = seed_user(f"{role}@example.com", role)
    headers = {
        "Authorization": f"Bearer {token_for(user_id, role)}",
        "X-Tenant-ID": str(tenant_id),
    }

    memberships_response = client.get("/api/v1/memberships", headers=headers)
    tenant_response = client.patch(
        "/api/v1/tenant",
        headers=headers,
        json={"name": "Unauthorized"},
    )

    assert memberships_response.status_code == 403
    assert tenant_response.status_code == 403


def test_forged_admin_jwt_cannot_escalate_viewer_membership():
    user_id, tenant_id = seed_user("forged@example.com", "viewer")
    with Session(engine) as db:
        membership_id = db.query(Membership.id).filter_by(
            user_id=user_id,
            tenant_id=tenant_id,
        ).scalar()

    response = client.patch(
        f"/api/v1/memberships/{membership_id}",
        headers={
            "Authorization": f"Bearer {token_for(user_id, 'admin')}",
            "X-Tenant-ID": str(tenant_id),
        },
        json={"role": "admin"},
    )

    assert response.status_code == 403


def test_non_admin_cannot_create_admin_membership():
    actor_id, actor_tenant_id = seed_user("actor@example.com", "analyst")
    target_id, _ = seed_user("target@example.com", "viewer")

    response = client.post(
        "/api/v1/memberships",
        headers={
            "Authorization": f"Bearer {token_for(actor_id, 'analyst')}",
            "X-Tenant-ID": str(actor_tenant_id),
        },
        json={"user_id": target_id, "role": "admin"},
    )

    assert response.status_code == 403


def test_cross_tenant_membership_id_is_not_accessible():
    actor_id, selected_tenant_id = seed_user("selected@example.com", "admin")
    target_id, other_tenant_id = seed_user("other@example.com", "viewer")
    with Session(engine) as db:
        membership_id = db.query(Membership.id).filter_by(
            user_id=target_id,
            tenant_id=other_tenant_id,
        ).scalar()

    response = client.patch(
        f"/api/v1/memberships/{membership_id}",
        headers={
            "Authorization": f"Bearer {token_for(actor_id, 'admin')}",
            "X-Tenant-ID": str(selected_tenant_id),
        },
        json={"role": "analyst"},
    )

    assert response.status_code == 404


def test_x_tenant_id_cannot_switch_admin_to_viewer_tenant():
    user_id, first_tenant_id = seed_user("multi@example.com", "admin")
    _, second_tenant_id = seed_user("second@example.com", "viewer")
    with Session(engine) as db:
        second_tenant = db.get(Tenant, second_tenant_id)
        db.add(
            Membership(
                tenant_id=second_tenant.id,
                user_id=user_id,
                role="viewer",
                is_active=True,
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/tenant",
        headers={
            "Authorization": f"Bearer {token_for(user_id, 'admin')}",
            "X-Tenant-ID": str(second_tenant_id),
        },
    )

    assert response.status_code == 403
    assert first_tenant_id != second_tenant_id


def test_tenant_update_cannot_change_another_tenant():
    actor_id, selected_tenant_id = seed_user("tenant-admin@example.com", "admin")
    _, other_tenant_id = seed_user("tenant-other@example.com", "viewer")

    response = client.patch(
        "/api/v1/tenant",
        headers={
            "Authorization": f"Bearer {token_for(actor_id, 'admin')}",
            "X-Tenant-ID": str(selected_tenant_id),
        },
        json={"slug": "changed-selected"},
    )

    assert response.status_code == 200
    with Session(engine) as db:
        other = db.get(Tenant, other_tenant_id)
        selected = db.get(Tenant, selected_tenant_id)
        assert selected.slug == "changed-selected"
        assert other.slug == "tenant-other-example-com"


def test_viewer_cannot_self_reactivate_or_elevate_membership():
    user_id, tenant_id = seed_user("self@example.com", "viewer")
    with Session(engine) as db:
        membership = db.query(Membership).filter_by(
            user_id=user_id,
            tenant_id=tenant_id,
        ).one()
        membership.is_active = False
        db.commit()
        membership_id = membership.id

    response = client.patch(
        f"/api/v1/memberships/{membership_id}",
        headers={
            "Authorization": f"Bearer {token_for(user_id, 'admin')}",
            "X-Tenant-ID": str(tenant_id),
        },
        json={"role": "admin", "is_active": True},
    )

    assert response.status_code == 403
    with Session(engine) as db:
        membership = db.get(Membership, membership_id)
        assert membership.role == "viewer"
        assert membership.is_active is False
