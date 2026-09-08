from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext
from app.api.routes.memberships import create_membership
from app.core.security import hash_password
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.membership import MembershipCreate


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

        from fastapi import HTTPException

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

        from fastapi import HTTPException

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

        from fastapi import HTTPException

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
