import threading
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.skipif(
    settings.environment != "test" or not settings.database_url.startswith("postgresql"),
    reason="Membership integrity integration tests require the PostgreSQL test database",
)


def seed_user(db, suffix: str) -> User:
    user = User(
        email=f"membership-integrity-{suffix}-{uuid4().hex}@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_tenant(db, suffix: str) -> Tenant:
    tenant = Tenant(
        name=f"Membership Integrity {suffix}",
        slug=f"membership-integrity-{suffix}-{uuid4().hex}",
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def seed_membership(db, user: User, tenant: Tenant, role: str = "viewer") -> Membership:
    membership = Membership(
        user_id=user.id,
        tenant_id=tenant.id,
        role=role,
        is_active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def cleanup(db, user_ids: list[int], tenant_ids: list[int]) -> None:
    db.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
    db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def test_duplicate_membership_same_user_and_tenant_is_rejected():
    db = SessionLocal()
    user = seed_user(db, "duplicate")
    tenant = seed_tenant(db, "duplicate")
    try:
        seed_membership(db, user, tenant)
        db.add(Membership(user_id=user.id, tenant_id=tenant.id, role="analyst", is_active=True))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.tenant_id == tenant.id,
            )
        ) is not None
    finally:
        cleanup(db, [user.id], [tenant.id])
        db.close()


def test_concurrent_duplicate_membership_insert_has_single_winner():
    setup_db = SessionLocal()
    user = seed_user(setup_db, "concurrent")
    tenant = seed_tenant(setup_db, "concurrent")
    setup_db.close()

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def attempt(role: str) -> None:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            db.add(
                Membership(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    role=role,
                    is_active=True,
                )
            )
            db.commit()
            results.append(("success", role))
        except IntegrityError:
            db.rollback()
            results.append(("integrity_error", role))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(exc)
        finally:
            db.close()

    first = threading.Thread(target=attempt, args=("admin",))
    second = threading.Thread(target=attempt, args=("analyst",))

    try:
        first.start()
        second.start()
        first.join(timeout=15)
        second.join(timeout=15)

        assert not first.is_alive()
        assert not second.is_alive()
        assert not errors
        assert sorted(result[0] for result in results) == [
            "integrity_error",
            "success",
        ]

        verification = SessionLocal()
        memberships = verification.scalars(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.tenant_id == tenant.id,
            )
        ).all()
        verification.close()

        assert len(memberships) == 1
        assert memberships[0].role in {"admin", "analyst"}
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user.id], [tenant.id])
        cleanup_db.close()


def test_deleting_tenant_cascades_memberships():
    db = SessionLocal()
    user = seed_user(db, "tenant-cascade")
    tenant = seed_tenant(db, "tenant-cascade")
    try:
        membership = seed_membership(db, user, tenant)
        db.delete(tenant)
        db.commit()
        assert db.get(Membership, membership.id) is None
        assert db.get(Tenant, tenant.id) is None
        assert db.get(User, user.id) is not None
    finally:
        cleanup(db, [user.id], [tenant.id])
        db.close()


def test_deleting_user_cascades_memberships():
    db = SessionLocal()
    user = seed_user(db, "user-cascade")
    tenant = seed_tenant(db, "user-cascade")
    try:
        membership = seed_membership(db, user, tenant)
        db.delete(user)
        db.commit()
        assert db.get(Membership, membership.id) is None
        assert db.get(User, user.id) is None
        assert db.get(Tenant, tenant.id) is not None
    finally:
        cleanup(db, [user.id], [tenant.id])
        db.close()


def test_multiple_tenants_and_users_remain_independent():
    db = SessionLocal()
    first_user = seed_user(db, "independent-a")
    second_user = seed_user(db, "independent-b")
    first_tenant = seed_tenant(db, "independent-a")
    second_tenant = seed_tenant(db, "independent-b")
    try:
        first_membership = seed_membership(db, first_user, first_tenant, role="admin")
        second_membership = seed_membership(db, first_user, second_tenant, role="viewer")
        third_membership = seed_membership(db, second_user, first_tenant, role="analyst")

        db.delete(first_tenant)
        db.commit()

        assert db.get(Membership, first_membership.id) is None
        assert db.get(Membership, third_membership.id) is None
        assert db.get(Membership, second_membership.id) is not None
        assert db.get(Tenant, second_tenant.id) is not None
        assert db.get(User, first_user.id) is not None
        assert db.get(User, second_user.id) is not None
    finally:
        cleanup(db, [first_user.id, second_user.id], [first_tenant.id, second_tenant.id])
        db.close()
