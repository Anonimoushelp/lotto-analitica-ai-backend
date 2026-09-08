from fastapi import HTTPException
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext
from app.api.routes.tenants import get_current_tenant, update_current_tenant
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantUpdate

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
User.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
AuditEvent.__table__.create(bind=engine)


def seed_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role="viewer",
        is_active=True,
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


def seed_membership(db: Session, user: User, tenant: Tenant) -> Membership:
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


def clean_db(db: Session) -> None:
    db.execute(delete(AuditEvent))
    db.execute(delete(Membership))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.commit()


def context(user: User, tenant: Tenant) -> TenantContext:
    return TenantContext(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_id=1,
        role="admin",
    )


def test_admin_can_read_current_tenant_from_context():
    with Session(engine) as db:
        user = seed_user(db, "tenant-read@example.com")
        tenant = seed_tenant(db, "tenant-read")
        seed_membership(db, user, tenant)

        result = get_current_tenant(db, context(user, tenant))

        assert result.id == tenant.id
        assert result.slug == "tenant-read"
        clean_db(db)


def test_tenant_update_uses_context_tenant_not_client_tenant_id():
    with Session(engine) as db:
        user = seed_user(db, "tenant-update@example.com")
        selected = seed_tenant(db, "selected-tenant")
        other = seed_tenant(db, "other-tenant")
        seed_membership(db, user, selected)

        updated = update_current_tenant(
            TenantUpdate(name="Updated Name"),
            db,
            context(user, selected),
        )

        db.refresh(other)
        assert updated.id == selected.id
        assert updated.name == "Updated Name"
        assert other.name == "Other-Tenant"
        clean_db(db)


def test_duplicate_tenant_slug_is_rejected():
    with Session(engine) as db:
        user = seed_user(db, "tenant-duplicate@example.com")
        selected = seed_tenant(db, "selected-slug")
        seed_tenant(db, "existing-slug")
        seed_membership(db, user, selected)

        try:
            update_current_tenant(
                TenantUpdate(slug="existing-slug"),
                db,
                context(user, selected),
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Expected duplicate tenant slug to be rejected")
        finally:
            clean_db(db)


def test_empty_tenant_update_is_rejected():
    with Session(engine) as db:
        user = seed_user(db, "tenant-empty@example.com")
        tenant = seed_tenant(db, "tenant-empty")
        seed_membership(db, user, tenant)

        try:
            update_current_tenant(TenantUpdate(), db, context(user, tenant))
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("Expected empty tenant update to be rejected")
        finally:
            clean_db(db)
