from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


def seed_user(db, email, role="admin"):
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


def seed_membership(db, tenant_id, user_id, role="admin"):
    membership = Membership(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        is_active=True,
    )
    db.add(membership)
    db.flush()
    return membership


def auth_token(user_id, role="admin"):
    return create_access_token(str(user_id), role)


def cleanup(db, user_ids, tenant_ids):
    if tenant_ids:
        db.execute(delete(Membership).where(Membership.tenant_id.in_(tenant_ids)))
        db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    if user_ids:
        db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def test_functional_encryption_denies_cross_tenant_header():
    db = SessionLocal()
    user = seed_user(db, "fe-e2e-header")
    tenant_a = seed_tenant(db, "fe-e2e-a")
    tenant_b = seed_tenant(db, "fe-e2e-b")
    seed_membership(db, tenant_a.id, user.id, role="analyst")
    user_id, tenant_a_id, tenant_b_id = user.id, tenant_a.id, tenant_b.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/functional-encryption/status",
            headers={
                "Authorization": f"Bearer {auth_token(user_id)}",
                "X-Tenant-ID": str(tenant_b_id),
            },
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_a_id, tenant_b_id])
        cleanup_db.close()


def test_functional_encryption_allows_authorized_tenant_and_fails_closed():
    db = SessionLocal()
    user = seed_user(db, "fe-e2e-authorized")
    tenant = seed_tenant(db, "fe-e2e-authorized")
    seed_membership(db, tenant.id, user.id, role="analyst")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.post(
            "/api/v1/functional-encryption/operations",
            json={"operation": "evaluate", "payload": {"ciphertext": "opaque"}},
            headers={"Authorization": f"Bearer {auth_token(user_id)}"},
        )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Functional Encryption provider is unavailable"
        }
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_functional_encryption_viewer_is_forbidden():
    db = SessionLocal()
    user = seed_user(db, "fe-e2e-viewer")
    tenant = seed_tenant(db, "fe-e2e-viewer")
    seed_membership(db, tenant.id, user.id, role="viewer")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/functional-encryption/status",
            headers={"Authorization": f"Bearer {auth_token(user_id, 'viewer')}"},
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_tee_denies_cross_tenant_header():
    db = SessionLocal()
    user = seed_user(db, "tee-e2e-header")
    tenant_a = seed_tenant(db, "tee-e2e-a")
    tenant_b = seed_tenant(db, "tee-e2e-b")
    seed_membership(db, tenant_a.id, user.id, role="analyst")
    user_id, tenant_a_id, tenant_b_id = user.id, tenant_a.id, tenant_b.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/tee/status",
            headers={
                "Authorization": f"Bearer {auth_token(user_id)}",
                "X-Tenant-ID": str(tenant_b_id),
            },
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_a_id, tenant_b_id])
        cleanup_db.close()


def test_tee_allows_authorized_tenant_and_fails_closed():
    db = SessionLocal()
    user = seed_user(db, "tee-e2e-authorized")
    tenant = seed_tenant(db, "tee-e2e-authorized")
    seed_membership(db, tenant.id, user.id, role="analyst")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.post(
            "/api/v1/tee/operations",
            json={"operation": "attest", "nonce": "0123456789abcdef"},
            headers={"Authorization": f"Bearer {auth_token(user_id)}"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "TEE attestation provider unavailable"}
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_tee_viewer_is_forbidden():
    db = SessionLocal()
    user = seed_user(db, "tee-e2e-viewer")
    tenant = seed_tenant(db, "tee-e2e-viewer")
    seed_membership(db, tenant.id, user.id, role="viewer")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/tee/status",
            headers={"Authorization": f"Bearer {auth_token(user_id, 'viewer')}"},
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()
