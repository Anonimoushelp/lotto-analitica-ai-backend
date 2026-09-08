from fastapi import HTTPException
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext
from app.api.routes.memberships import create_membership, update_membership
from app.core.security import hash_password
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.membership import MembershipCreate, MembershipUpdate


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
User.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)


def seed_user(db: Session, email: str, active: bool = True) -> User:
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_tenant(db: Session, slug: str) -> Tenant:
    tenant = Tenant(name=slug.title(), slug=slug, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def seed_membership(
    db: Session, user: User, tenant: Tenant, role: str = "admin"
) -> Membership:
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


def clean_db(db: Session) -> None:
    db.execute(delete(Membership))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.commit()


def context(user: User, tenant: Tenant, role: str = "admin") -> TenantContext:
    return TenantContext(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_id=1,
        role=role,
    )


def test_admin_can_create_membership_in_selected_tenant():
    with Session(engine) as db:
        actor = seed_user(db, "actor@example.com")
        target = seed_user(db, "target@example.com")
        tenant = seed_tenant(db, "acme")

        membership = create_membership(
            MembershipCreate(user_id=target.id, role="analyst"),
            db,
            context(actor, tenant),
        )

        assert membership.tenant_id == tenant.id
        assert membership.user_id == target.id
        assert membership.role == "analyst"
        assert membership.is_active is True
        clean_db(db)


def test_membership_creation_uses_context_tenant_not_client_payload():
    with Session(engine) as db:
        actor = seed_user(db, "actor2@example.com")
        target = seed_user(db, "target2@example.com")
        first = seed_tenant(db, "first")
        second = seed_tenant(db, "second")

        payload = MembershipCreate(user_id=target.id, role="viewer")
        membership = create_membership(payload, db, context(actor, second))

        assert membership.tenant_id == second.id
        assert membership.tenant_id != first.id
        clean_db(db)


def test_duplicate_membership_is_rejected():
    with Session(engine) as db:
        actor = seed_user(db, "actor3@example.com")
        target = seed_user(db, "target3@example.com")
        tenant = seed_tenant(db, "duplicate")
        seed_membership(db, target, tenant)

        try:
            create_membership(
                MembershipCreate(user_id=target.id, role="viewer"),
                db,
                context(actor, tenant),
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Expected duplicate membership to be rejected")
        finally:
            clean_db(db)


def test_nonexistent_user_is_rejected():
    with Session(engine) as db:
        actor = seed_user(db, "actor4@example.com")
        tenant = seed_tenant(db, "missing-user")

        try:
            create_membership(
                MembershipCreate(user_id=999999, role="viewer"),
                db,
                context(actor, tenant),
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected nonexistent user to be rejected")
        finally:
            clean_db(db)


def test_inactive_user_is_rejected():
    with Session(engine) as db:
        actor = seed_user(db, "actor5@example.com")
        target = seed_user(db, "inactive@example.com", active=False)
        tenant = seed_tenant(db, "inactive-user")

        try:
            create_membership(
                MembershipCreate(user_id=target.id, role="viewer"),
                db,
                context(actor, tenant),
            )
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("Expected inactive user to be rejected")
        finally:
            clean_db(db)


def test_admin_can_update_membership_role_and_active_state():
    with Session(engine) as db:
        actor = seed_user(db, "actor6@example.com")
        target = seed_user(db, "target6@example.com")
        tenant = seed_tenant(db, "update")
        membership = seed_membership(db, target, tenant, role="viewer")

        updated = update_membership(
            membership.id,
            MembershipUpdate(role="analyst", is_active=False),
            db,
            context(actor, tenant),
        )

        assert updated.role == "analyst"
        assert updated.is_active is False
        clean_db(db)


def test_update_cannot_access_membership_from_another_tenant():
    with Session(engine) as db:
        actor = seed_user(db, "actor7@example.com")
        target = seed_user(db, "target7@example.com")
        selected = seed_tenant(db, "selected")
        other = seed_tenant(db, "other")
        membership = seed_membership(db, target, other, role="viewer")

        try:
            update_membership(
                membership.id,
                MembershipUpdate(role="analyst"),
                db,
                context(actor, selected),
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected cross-tenant membership update to be rejected")
        finally:
            clean_db(db)


def test_last_active_admin_cannot_be_demoted():
    with Session(engine) as db:
        actor = seed_user(db, "actor8@example.com")
        tenant = seed_tenant(db, "last-admin")
        membership = seed_membership(db, actor, tenant, role="admin")

        try:
            update_membership(
                membership.id,
                MembershipUpdate(role="viewer"),
                db,
                context(actor, tenant),
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Expected last active admin protection")
        finally:
            clean_db(db)


def test_last_active_admin_cannot_be_deactivated():
    with Session(engine) as db:
        actor = seed_user(db, "actor9@example.com")
        tenant = seed_tenant(db, "last-admin-active")
        membership = seed_membership(db, actor, tenant, role="admin")

        try:
            update_membership(
                membership.id,
                MembershipUpdate(is_active=False),
                db,
                context(actor, tenant),
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Expected last active admin protection")
        finally:
            clean_db(db)


def test_admin_can_demote_admin_when_another_active_admin_exists():
    with Session(engine) as db:
        first_admin = seed_user(db, "admin-a@example.com")
        second_admin = seed_user(db, "admin-b@example.com")
        tenant = seed_tenant(db, "two-admins")
        first_membership = seed_membership(db, first_admin, tenant, role="admin")
        seed_membership(db, second_admin, tenant, role="admin")

        updated = update_membership(
            first_membership.id,
            MembershipUpdate(role="viewer"),
            db,
            context(second_admin, tenant),
        )

        assert updated.role == "viewer"
        assert updated.is_active is True
        clean_db(db)


def test_empty_membership_update_is_rejected():
    with Session(engine) as db:
        actor = seed_user(db, "actor10@example.com")
        target = seed_user(db, "target10@example.com")
        tenant = seed_tenant(db, "empty-update")
        membership = seed_membership(db, target, tenant, role="viewer")

        try:
            update_membership(
                membership.id,
                MembershipUpdate(),
                db,
                context(actor, tenant),
            )
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("Expected empty membership update to be rejected")
        finally:
            clean_db(db)
