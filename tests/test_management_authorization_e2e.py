import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
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
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
User.__table__.create(bind=engine)


client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def cleanup():
    db = TestingSessionLocal()
    db.execute(delete(Membership))
    db.execute(delete(User))
    db.execute(delete(Tenant))
    db.commit()
    db.close()


def seed_user(role: str, tenant_role: str | None = None):
    db = TestingSessionLocal()
    tenant = Tenant(name=f"Tenant {role}", slug=f"tenant-{role}")
    user = User(
        email=f"{role}@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role=role,
        is_active=True,
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(
        Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=tenant_role or role,
            is_active=True,
        )
    )
    db.commit()
    user_id = user.id
    tenant_id = tenant.id
    db.close()
    return user_id, tenant_id


def seed_two_tenants():
    db = TestingSessionLocal()
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    user = User(
        email="admin@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
    )
    other = User(
        email="other@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=True,
    )
    db.add_all([tenant_a, tenant_b, user, other])
    db.flush()
    membership_a = Membership(
        tenant_id=tenant_a.id,
        user_id=user.id,
        role="admin",
        is_active=True,
    )
    membership_b = Membership(
        tenant_id=tenant_b.id,
        user_id=other.id,
        role="viewer",
        is_active=True,
    )
    db.add_all([membership_a, membership_b])
    db.commit()
    result = (user.id, tenant_a.id, tenant_b.id, membership_b.id)
    db.close()
    return result


def seed_multi_tenant_user():
    db = TestingSessionLocal()
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    admin = User(
        email="admin@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
    )
    target = User(
        email="target@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=True,
    )
    db.add_all([tenant_a, tenant_b, admin, target])
    db.flush()
    membership_a = Membership(
        tenant_id=tenant_a.id,
        user_id=admin.id,
        role="admin",
        is_active=True,
    )
    target_membership = Membership(
        tenant_id=tenant_b.id,
        user_id=target.id,
        role="viewer",
        is_active=True,
    )
    db.add_all([membership_a, target_membership])
    db.commit()
    result = (admin.id, tenant_a.id, tenant_b.id, target.id, target_membership.id)
    db.close()
    return result


def auth_header(user_id: int, role_claim: str) -> dict[str, str]:
    token = create_access_token(str(user_id), role_claim)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def isolate_test_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    cleanup()
    try:
        yield
    finally:
        cleanup()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_membership_management_rejects_viewer_and_analyst():
    for role in ("viewer", "analyst"):
        user_id, tenant_id = seed_user(role)
        headers = auth_header(user_id, role)
        response = client.get(
            "/api/v1/memberships",
            headers={**headers, "X-Tenant-ID": str(tenant_id)},
        )
        assert response.status_code == 403
        cleanup()


def test_membership_management_rejects_forged_admin_claim_for_viewer_membership():
    user_id, tenant_id = seed_user("viewer")
    response = client.get(
        "/api/v1/memberships",
        headers={
            **auth_header(user_id, "admin"),
            "X-Tenant-ID": str(tenant_id),
        },
    )
    assert response.status_code == 403


def test_tenant_management_rejects_viewer_and_analyst():
    for role in ("viewer", "analyst"):
        user_id, tenant_id = seed_user(role)
        response = client.patch(
            "/api/v1/tenant",
            headers={
                **auth_header(user_id, role),
                "X-Tenant-ID": str(tenant_id),
            },
            json={"name": "Unauthorized"},
        )
        assert response.status_code == 403
        cleanup()


def test_tenant_management_rejects_forged_admin_claim_for_viewer_membership():
    user_id, tenant_id = seed_user("viewer")
    response = client.patch(
        "/api/v1/tenant",
        headers={
            **auth_header(user_id, "admin"),
            "X-Tenant-ID": str(tenant_id),
        },
        json={"name": "Unauthorized"},
    )
    assert response.status_code == 403


def test_tenant_selection_cannot_cross_into_unowned_tenant():
    user_id, _, tenant_b_id, _ = seed_two_tenants()
    response = client.patch(
        "/api/v1/tenant",
        headers={
            **auth_header(user_id, "admin"),
            "X-Tenant-ID": str(tenant_b_id),
        },
        json={"name": "Cross Tenant"},
    )
    assert response.status_code == 403


def test_membership_id_cannot_cross_tenant_boundary():
    user_id, tenant_a_id, _, membership_b_id = seed_two_tenants()
    response = client.patch(
        f"/api/v1/memberships/{membership_b_id}",
        headers={
            **auth_header(user_id, "admin"),
            "X-Tenant-ID": str(tenant_a_id),
        },
        json={"role": "admin"},
    )
    assert response.status_code == 404


def test_adding_multi_tenant_membership_preserves_existing_membership():
    admin_id, tenant_a_id, tenant_b_id, target_id, existing_membership_id = seed_multi_tenant_user()
    response = client.post(
        "/api/v1/memberships",
        headers={
            **auth_header(admin_id, "admin"),
            "X-Tenant-ID": str(tenant_a_id),
        },
        json={"user_id": target_id, "role": "analyst"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["tenant_id"] == tenant_a_id
    assert created["user_id"] == target_id
    assert created["role"] == "analyst"

    db = TestingSessionLocal()
    memberships = list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == target_id)
            .order_by(Membership.tenant_id)
        ).all()
    )
    existing = db.get(Membership, existing_membership_id)
    assert len(memberships) == 2
    assert existing is not None
    assert existing.tenant_id == tenant_b_id
    assert existing.role == "viewer"
    assert existing.is_active is True
    db.close()
