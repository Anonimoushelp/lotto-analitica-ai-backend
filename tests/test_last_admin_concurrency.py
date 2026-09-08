import threading
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.dependencies.tenant import TenantContext
from app.api.routes.memberships import update_membership
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.membership import MembershipUpdate

pytestmark = pytest.mark.skipif(
    settings.environment != "test" or not settings.database_url.startswith("postgresql"),
    reason="Last-admin concurrency integration test requires the PostgreSQL test database",
)


def seed_user(db, suffix: str) -> User:
    user = User(
        email=f"last-admin-concurrency-{suffix}-{uuid4().hex}@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_tenant(db) -> Tenant:
    tenant = Tenant(
        name="Last Admin Concurrency",
        slug=f"last-admin-concurrency-{uuid4().hex}",
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def seed_membership(db, user: User, tenant: Tenant) -> Membership:
    membership = Membership(
        user_id=user.id,
        tenant_id=tenant.id,
        role="admin",
        is_active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def cleanup(db, user_ids: list[int], tenant_id: int) -> None:
    db.execute(delete(Membership).where(Membership.tenant_id == tenant_id))
    db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def test_concurrent_last_admin_removals_preserve_one_active_admin():
    setup_db = SessionLocal()
    first_user = seed_user(setup_db, "first")
    second_user = seed_user(setup_db, "second")
    tenant = seed_tenant(setup_db)
    first_membership = seed_membership(setup_db, first_user, tenant)
    second_membership = seed_membership(setup_db, second_user, tenant)
    first_user_id = first_user.id
    second_user_id = second_user.id
    tenant_id = tenant.id
    first_membership_id = first_membership.id
    second_membership_id = second_membership.id
    setup_db.close()

    barrier = threading.Barrier(2)
    results: list[tuple[str, str]] = []
    errors: list[Exception] = []

    def attempt(membership_id: int, actor_id: int) -> None:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            context = TenantContext(
                user_id=actor_id,
                tenant_id=tenant_id,
                membership_id=membership_id,
                role="admin",
            )
            update_membership(
                membership_id,
                MembershipUpdate(role="viewer"),
                db,
                context,
            )
            results.append(("success", str(membership_id)))
        except HTTPException as exc:
            results.append(("http_error", f"{membership_id}:{exc.status_code}"))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(exc)
        finally:
            db.close()

    first = threading.Thread(
        target=attempt,
        args=(first_membership_id, first_user_id),
    )
    second = threading.Thread(
        target=attempt,
        args=(second_membership_id, second_user_id),
    )

    try:
        first.start()
        second.start()
        first.join(timeout=15)
        second.join(timeout=15)

        assert not first.is_alive()
        assert not second.is_alive()
        assert not errors
        assert sorted(result[0] for result in results) == ["http_error", "success"]
        assert any(
            result[0] == "http_error" and result[1].endswith(":409")
            for result in results
        )

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
        cleanup(cleanup_db, [first_user_id, second_user_id], tenant_id)
        cleanup_db.close()
