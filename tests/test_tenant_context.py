import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext, get_tenant_context
from app.core.security import hash_password
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
User.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)


def seed_user(db: Session, email: str = "user@example.com") -> User:
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


def seed_tenant(db: Session, slug: str, active: bool = True) -> Tenant:
    tenant = Tenant(name=slug.title(), slug=slug, is_active=active)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def seed_membership(
    db: Session,
    user: User,
    tenant: Tenant,
    role: str = "viewer",
    active: bool = True,
) -> Membership:
    membership = Membership(
        user_id=user.id,
        tenant_id=tenant.id,
        role=role,
        is_active=active,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@pytest.fixture

def db():
    session = Session(engine)
    try:
        yield session
    finally:
        session.execute(delete(Membership))
        session.execute(delete(Tenant))
        session.execute(delete(User))
        session.commit()
        session.close()


def test_single_active_membership_is_selected_automatically(db):
    user = seed_user(db)
    tenant = seed_tenant(db, "acme")
    membership = seed_membership(db, user, tenant, role="analyst")

    context = get_tenant_context(current_user=user, db=db)

    assert context == TenantContext(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_id=membership.id,
        role="analyst",
    )


def test_multiple_active_memberships_require_explicit_selection(db):
    user = seed_user(db)
    first = seed_tenant(db, "first")
    second = seed_tenant(db, "second")
    seed_membership(db, user, first)
    seed_membership(db, user, second)

    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(current_user=user, db=db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Tenant selection required"


def test_explicit_selection_returns_only_authorized_membership(db):
    user = seed_user(db)
    first = seed_tenant(db, "first")
    second = seed_tenant(db, "second")
    seed_membership(db, user, first, role="viewer")
    second_membership = seed_membership(db, user, second, role="admin")

    context = get_tenant_context(
        current_user=user,
        db=db,
        x_tenant_id=second.id,
    )

    assert context.tenant_id == second.id
    assert context.membership_id == second_membership.id
    assert context.role == "admin"


def test_unknown_or_unauthorized_tenant_is_forbidden(db):
    user = seed_user(db)
    tenant = seed_tenant(db, "authorized")
    seed_membership(db, user, tenant)

    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(current_user=user, db=db, x_tenant_id=999999)

    assert exc_info.value.status_code == 403


def test_inactive_membership_is_forbidden(db):
    user = seed_user(db)
    tenant = seed_tenant(db, "inactive-membership")
    seed_membership(db, user, tenant, active=False)

    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_inactive_tenant_is_forbidden(db):
    user = seed_user(db)
    tenant = seed_tenant(db, "inactive-tenant", active=False)
    seed_membership(db, user, tenant)

    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_membership_role_is_authoritative_over_user_role(db):
    user = seed_user(db)
    user.role = "admin"
    tenant = seed_tenant(db, "role-source")
    membership = seed_membership(db, user, tenant, role="viewer")

    context = get_tenant_context(current_user=user, db=db)

    assert context.role == membership.role
    assert context.role == "viewer"
