import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from fastapi.testclient import TestClient


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
    db.query(Membership).delete()
    db.query(User).delete()
    db.query(Tenant).delete()
    db.commit()
    db.close()


def auth_header(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user_id), 'admin')}"}


@pytest.fixture(autouse=True)
def isolate_database():
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    cleanup()
    try:
        yield
    finally:
        cleanup()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def test_adding_multi_tenant_membership_preserves_existing_membership():
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
    db.add_all(
        [
            Membership(tenant_id=tenant_a.id, user_id=admin.id, role="admin", is_active=True),
            Membership(tenant_id=tenant_b.id, user_id=target.id, role="viewer", is_active=True),
        ]
    )
    db.commit()
    admin_id, tenant_a_id, tenant_b_id, target_id = admin.id, tenant_a.id, tenant_b.id, target.id
    db.close()

    response = client.post(
        "/api/v1/memberships",
        headers={**auth_header(admin_id), "X-Tenant-ID": str(tenant_a_id)},
        json={"user_id": target_id, "role": "analyst"},
    )
    assert response.status_code == 201

    db = TestingSessionLocal()
    memberships = list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == target_id)
            .order_by(Membership.tenant_id)
        ).all()
    )
    assert len(memberships) == 2
    by_tenant = {membership.tenant_id: membership for membership in memberships}
    assert by_tenant[tenant_a_id].role == "analyst"
    assert by_tenant[tenant_a_id].is_active is True
    assert by_tenant[tenant_b_id].role == "viewer"
    assert by_tenant[tenant_b_id].is_active is True
    db.close()
