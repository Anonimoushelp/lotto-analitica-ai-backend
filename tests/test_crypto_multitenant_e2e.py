from sqlalchemy import delete
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


def seed_user(db, email, role="viewer"):
    user = User(
        email=email,
        password_hash=hash_password("test-password"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def seed_tenant(db, slug):
    tenant = Tenant(name=f"Tenant {slug}", slug=slug, is_active=True)
    db.add(tenant)
    db.flush()
    return tenant


def seed_membership(db, tenant_id, user_id, role):
    membership = Membership(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        is_active=True,
    )
    db.add(membership)
    db.flush()
    return membership


def auth_headers(user_id, role="viewer", tenant_id=None):
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id), role)}"}
    if tenant_id is not None:
        headers["X-Tenant-ID"] = str(tenant_id)
    return headers


def cleanup(db, user_ids, tenant_ids):
    if tenant_ids:
        db.execute(delete(Membership).where(Membership.tenant_id.in_(tenant_ids)))
        db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    if user_ids:
        db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def test_tee_rejects_cross_tenant_header_before_operation():
    db = SessionLocal()
    user = seed_user(db, "tee-cross-tenant", role="analyst")
    tenant_a = seed_tenant(db, "tee-cross-a")
    tenant_b = seed_tenant(db, "tee-cross-b")
    seed_membership(db, tenant_a.id, user.id, role="analyst")
    user_id, tenant_a_id, tenant_b_id = user.id, tenant_a.id, tenant_b.id
    db.commit()
    db.close()
    try:
        response = client.post(
            "/api/v1/tee/operations",
            headers=auth_headers(user_id, "analyst", tenant_b_id),
            json={"operation": "attest", "nonce": "0123456789abcdef"},
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_a_id, tenant_b_id])
        cleanup_db.close()


def test_tee_membership_role_is_authoritative_over_user_role():
    db = SessionLocal()
    user = seed_user(db, "tee-role", role="admin")
    tenant = seed_tenant(db, "tee-role")
    seed_membership(db, tenant.id, user.id, role="viewer")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/tee/status",
            headers=auth_headers(user_id, "admin", tenant_id),
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_tee_authorized_membership_reaches_provider_fail_closed():
    db = SessionLocal()
    user = seed_user(db, "tee-authorized", role="viewer")
    tenant = seed_tenant(db, "tee-authorized")
    seed_membership(db, tenant.id, user.id, role="analyst")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.post(
            "/api/v1/tee/operations",
            headers=auth_headers(user_id, "viewer", tenant_id),
            json={"operation": "attest", "nonce": "0123456789abcdef"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "TEE attestation provider unavailable"}
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_functional_encryption_rejects_cross_tenant_header():
    db = SessionLocal()
    user = seed_user(db, "fe-cross-tenant", role="analyst")
    tenant_a = seed_tenant(db, "fe-cross-a")
    tenant_b = seed_tenant(db, "fe-cross-b")
    seed_membership(db, tenant_a.id, user.id, role="analyst")
    user_id, tenant_a_id, tenant_b_id = user.id, tenant_a.id, tenant_b.id
    db.commit()
    db.close()
    try:
        response = client.post(
            "/api/v1/functional-encryption/operations",
            headers=auth_headers(user_id, "analyst", tenant_b_id),
            json={"operation": "encrypt", "payload": {"value": "test"}},
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_a_id, tenant_b_id])
        cleanup_db.close()


def test_functional_encryption_membership_role_is_authoritative():
    db = SessionLocal()
    user = seed_user(db, "fe-role", role="admin")
    tenant = seed_tenant(db, "fe-role")
    seed_membership(db, tenant.id, user.id, role="viewer")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/functional-encryption/status",
            headers=auth_headers(user_id, "admin", tenant_id),
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_functional_encryption_authorized_membership_reaches_provider_fail_closed():
    db = SessionLocal()
    user = seed_user(db, "fe-authorized", role="viewer")
    tenant = seed_tenant(db, "fe-authorized")
    seed_membership(db, tenant.id, user.id, role="analyst")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.post(
            "/api/v1/functional-encryption/operations",
            headers=auth_headers(user_id, "viewer", tenant_id),
            json={"operation": "evaluate", "payload": {"ciphertext": "opaque"}},
        )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Functional Encryption provider is unavailable"
        }
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()
