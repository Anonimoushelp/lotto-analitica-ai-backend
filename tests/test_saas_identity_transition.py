from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.lottery import Lottery
from app.models.membership import Membership
from app.models.plan import Plan
from app.models.tenant import Tenant
from app.models.user import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Plan.__table__.create(bind=engine)
Tenant.__table__.create(bind=engine)
User.__table__.create(bind=engine)
Membership.__table__.create(bind=engine)
Lottery.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def setup_function():
    app.dependency_overrides[get_db] = override_get_db


def teardown_function():
    db = TestingSessionLocal()
    db.execute(delete(Lottery))
    db.execute(delete(Membership))
    db.execute(delete(User))
    db.execute(delete(Tenant))
    db.execute(delete(Plan))
    db.commit()
    db.close()
    app.dependency_overrides.pop(get_db, None)


def seed_user(user_role: str, membership_role: str) -> tuple[int, int]:
    db = TestingSessionLocal()
    plan = db.scalar(select(Plan).where(Plan.code == "free"))
    if plan is None:
        plan = Plan(code="free", name="Free", is_active=True)
        db.add(plan)
        db.flush()

    tenant = Tenant(
        name="SaaS Test Tenant",
        slug=f"saas-{user_role}-{membership_role}",
        plan_id=plan.id,
    )
    user = User(
        email=f"{user_role}-{membership_role}@example.com",
        password_hash=hash_password("StrongTestPassword123!"),
        role=user_role,
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=membership_role))
    db.commit()
    ids = (user.id, tenant.id)
    db.close()
    return ids


def test_membership_role_overrides_legacy_user_role_for_saas_route():
    user_id, tenant_id = seed_user("admin", "viewer")
    token = create_access_token(str(user_id), "admin")

    response = client.get(
        "/api/v1/lotteries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 403


def test_membership_admin_is_authoritative_even_when_legacy_user_role_is_viewer():
    user_id, tenant_id = seed_user("viewer", "admin")
    token = create_access_token(str(user_id), "viewer")

    response = client.get(
        "/api/v1/lotteries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": str(tenant_id),
        },
    )

    assert response.status_code == 200


def test_token_role_claim_cannot_escalate_saas_permissions():
    user_id, tenant_id = seed_user("viewer", "viewer")
    forged_role_token = create_access_token(str(user_id), "admin")

    response = client.post(
        "/api/v1/lotteries",
        headers={
            "Authorization": f"Bearer {forged_role_token}",
            "X-Tenant-ID": str(tenant_id),
        },
        json={"name": "Escalation Attempt", "code": "ESC", "country": "CO"},
    )

    assert response.status_code == 403
