from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext
from app.api.routes.memberships import (
    create_membership,
    delete_membership,
    update_membership,
)
from app.api.routes.tenants import update_current_tenant
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.membership import Membership
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.membership import MembershipCreate, MembershipUpdate
from app.schemas.tenant import TenantUpdate

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Plan.__table__.create(bind=engine)
PlanQuota.__table__.create(bind=engine)
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
    plan = db.scalar(select(Plan).where(Plan.code == "free"))
    if plan is None:
        plan = Plan(code="free", name="Free", is_active=True)
        db.add(plan)
        db.flush()
    tenant = Tenant(name=slug.title(), slug=slug, is_active=True, plan_id=plan.id)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def seed_membership(db: Session, user: User, tenant: Tenant, role: str = "admin") -> Membership:
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


def context(user: User, tenant: Tenant, membership: Membership) -> TenantContext:
    return TenantContext(
        user_id=user.id,
        tenant_id=tenant.id,
        membership_id=membership.id,
        role="admin",
    )


def clean_db(db: Session) -> None:
    db.execute(delete(AuditEvent))
    db.execute(delete(Membership))
    db.execute(delete(Tenant))
    db.execute(delete(User))
    db.execute(delete(PlanQuota))
    db.execute(delete(Plan))
    db.commit()


def test_membership_create_persists_audit_event_atomically():
    with Session(engine) as db:
        actor = seed_user(db, "audit-create-actor@example.com")
        target = seed_user(db, "audit-create-target@example.com")
        tenant = seed_tenant(db, "audit-create")
        actor_membership = seed_membership(db, actor, tenant)

        membership = create_membership(
            MembershipCreate(user_id=target.id, role="viewer"),
            db,
            context(actor, tenant, actor_membership),
        )

        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant.id,
                AuditEvent.resource_id == str(membership.id),
            )
        )
        assert event is not None
        assert event.actor_user_id == actor.id
        assert event.action == "membership.create"
        assert event.resource_type == "membership"
        assert event.outcome == "success"
        clean_db(db)


def test_membership_update_and_deactivate_persist_audit_events():
    with Session(engine) as db:
        actor = seed_user(db, "audit-update-actor@example.com")
        target = seed_user(db, "audit-update-target@example.com")
        tenant = seed_tenant(db, "audit-update")
        actor_membership = seed_membership(db, actor, tenant)
        target_membership = seed_membership(db, target, tenant, role="analyst")

        update_membership(
            target_membership.id,
            MembershipUpdate(role="viewer"),
            db,
            context(actor, tenant, actor_membership),
        )
        delete_membership(
            target_membership.id,
            db,
            context(actor, tenant, actor_membership),
        )

        events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.tenant_id == tenant.id)
                .order_by(AuditEvent.id)
            ).all()
        )
        assert [event.action for event in events] == [
            "membership.update",
            "membership.deactivate",
        ]
        assert all(event.actor_user_id == actor.id for event in events)
        clean_db(db)


def test_tenant_update_persists_audit_event():
    with Session(engine) as db:
        actor = seed_user(db, "audit-tenant-actor@example.com")
        tenant = seed_tenant(db, "audit-tenant")
        actor_membership = seed_membership(db, actor, tenant)

        update_current_tenant(
            TenantUpdate(name="Audited Tenant"),
            db,
            context(actor, tenant, actor_membership),
        )

        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant.id,
                AuditEvent.action == "tenant.update",
            )
        )
        assert event is not None
        assert event.actor_user_id == actor.id
        assert event.resource_type == "tenant"
        assert event.resource_id == str(tenant.id)
        assert "Audited Tenant" in event.details
        clean_db(db)
