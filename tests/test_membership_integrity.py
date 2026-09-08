import threading
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.routes.memberships import _lock_tenant_for_admin_change
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
    user_id = user.id
    tenant_id = tenant.id
    try:
        seed_membership(db, user, tenant)
        db.add(Membership(user_id=user_id, tenant_id=tenant_id, role="analyst", is_active=True))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
            )
        ) is not None
    finally:
        cleanup(db, [user_id], [tenant_id])
        db.close()


def test_concurrent_duplicate_membership_insert_has_single_winner():
    setup_db = SessionLocal()
    user = seed_user(setup_db, "concurrent")
    tenant = seed_tenant(setup_db, "concurrent")
    user_id = user.id
    tenant_id = tenant.id
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
                    user_id=user_id,
                    tenant_id=tenant_id,
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
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
            )
        ).all()
        verification.close()

        assert len(memberships) == 1
        assert memberships[0].role in {"admin", "analyst"}
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_concurrent_admin_change_lock_prevents_zero_active_admins():
    setup_db = SessionLocal()
    first_admin = seed_user(setup_db, "concurrent-admin-a")
    second_admin = seed_user(setup_db, "concurrent-admin-b")
    tenant = seed_tenant(setup_db, "concurrent-admin")
    first_membership = seed_membership(setup_db, first_admin, tenant, role="admin")
    second_membership = seed_membership(setup_db, second_admin, tenant, role="admin")
    first_admin_id = first_admin.id
    second_admin_id = second_admin.id
    tenant_id = tenant.id
    first_membership_id = first_membership.id
    second_membership_id = second_membership.id
    setup_db.close()

    first_locked = threading.Event()
    release_first = threading.Event()
    results = []
    errors = []

    def demote_and_hold(membership_id: int) -> None:
        db = SessionLocal()
        try:
            _lock_tenant_for_admin_change(db, tenant_id)
            first_locked.set()
            if not release_first.wait(timeout=15):
                raise TimeoutError("first transaction was not released")
            active_admins = db.scalar(
                select(Membership.id).where(
                    Membership.tenant_id == tenant_id,
                    Membership.role == "admin",
                    Membership.is_active.is_(True),
                ).limit(2)
            )
            if active_admins is None:
                results.append("blocked")
                db.rollback()
                return
            db.get(Membership, membership_id).role = "viewer"
            db.commit()
            results.append("demoted")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(exc)
        finally:
            db.close()

    def demote_after_lock(membership_id: int) -> None:
        db = SessionLocal()
        try:
            if not first_locked.wait(timeout=15):
                raise TimeoutError("first transaction did not acquire tenant lock")
            _lock_tenant_for_admin_change(db, tenant_id)
            active_admins = db.scalar(
                select(Membership.id).where(
                    Membership.tenant_id == tenant_id,
                    Membership.role == "admin",
                    Membership.is_active.is_(True),
                ).limit(2)
            )
            if active_admins is None:
                results.append("blocked")
                db.rollback()
                return
            db.get(Membership, membership_id).role = "viewer"
            db.commit()
            results.append("demoted")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(exc)
        finally:
            db.close()

    first = threading.Thread(target=demote_and_hold, args=(first_membership_id,))
    second = threading.Thread(target=demote_after_lock, args=(second_membership_id,))

    try:
        first.start()
        assert first_locked.wait(timeout=15)
        second.start()
        release_first.set()
        first.join(timeout=20)
        second.join(timeout=20)

        assert not first.is_alive()
        assert not second.is_alive()
        assert not errors
        assert sorted(results) == ["blocked", "demoted"]

        verification = SessionLocal()
        active_admins = verification.scalars(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.role == "admin",
                Membership.is_active.is_(True),
            )
        ).all()
        verification.close()

        assert len(active_admins) == 1
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [first_admin_id, second_admin_id], [tenant_id])
        cleanup_db.close()


def test_deleting_tenant_cascades_memberships():
    db = SessionLocal()
    user = seed_user(db, "tenant-cascade")
    tenant = seed_tenant(db, "tenant-cascade")
    user_id = user.id
    tenant_id = tenant.id
    try:
        membership = seed_membership(db, user, tenant)
        membership_id = membership.id
        db.delete(tenant)
        db.commit()
        assert db.get(Membership, membership_id) is None
        assert db.get(Tenant, tenant_id) is None
        assert db.get(User, user_id) is not None
    finally:
        cleanup(db, [user_id], [tenant_id])
        db.close()


def test_deleting_user_cascades_memberships():
    db = SessionLocal()
    user = seed_user(db, "user-cascade")
    tenant = seed_tenant(db, "user-cascade")
    user_id = user.id
    tenant_id = tenant.id
    try:
        membership = seed_membership(db, user, tenant)
        membership_id = membership.id
        db.delete(user)
        db.commit()
        assert db.get(Membership, membership_id) is None
        assert db.get(User, user_id) is None
        assert db.get(Tenant, tenant_id) is not None
    finally:
        cleanup(db, [user_id], [tenant_id])
        db.close()


def test_multiple_tenants_and_users_remain_independent():
    db = SessionLocal()
    first_user = seed_user(db, "independent-a")
    second_user = seed_user(db, "independent-b")
    first_tenant = seed_tenant(db, "independent-a")
    second_tenant = seed_tenant(db, "independent-b")
    first_user_id = first_user.id
    second_user_id = second_user.id
    first_tenant_id = first_tenant.id
    second_tenant_id = second_tenant.id
    try:
        first_membership = seed_membership(db, first_user, first_tenant, role="admin")
        second_membership = seed_membership(db, first_user, second_tenant, role="viewer")
        third_membership = seed_membership(db, second_user, first_tenant, role="analyst")
        first_membership_id = first_membership.id
        second_membership_id = second_membership.id
        third_membership_id = third_membership.id

        db.delete(first_tenant)
        db.commit()

        assert db.get(Membership, first_membership_id) is None
        assert db.get(Membership, third_membership_id) is None
        assert db.get(Membership, second_membership_id) is not None
        assert db.get(Tenant, second_tenant_id) is not None
        assert db.get(User, first_user_id) is not None
        assert db.get(User, second_user_id) is not None
    finally:
        cleanup(db, [first_user_id, second_user_id], [first_tenant_id, second_tenant_id])
        db.close()
