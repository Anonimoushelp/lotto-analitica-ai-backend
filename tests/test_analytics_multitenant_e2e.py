from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.tenant import TenantContext, get_tenant_context
from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.membership import Membership
from app.models.plan import Plan
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
    plan = db.scalar(select(Plan).where(Plan.code == "free"))
    if plan is None:
        plan = Plan(code="free", name="Free", is_active=True)
        db.add(plan)
        db.flush()
    tenant = Tenant(name=f"Tenant {slug}", slug=slug, is_active=True, plan_id=plan.id)
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


def seed_lottery(db, tenant_id, code):
    lottery = Lottery(
        tenant_id=tenant_id,
        code=code,
        name=f"Lottery {code}",
        country="CO",
        active=True,
    )
    db.add(lottery)
    db.flush()
    return lottery


def seed_draw(db, lottery_id, draw_number):
    draw = LotteryDraw(
        lottery_id=lottery_id,
        draw_number=str(draw_number),
        draw_date=date(2026, 1, draw_number),
        main_numbers=[1, 2, 3, 4, 5],
    )
    db.add(draw)
    db.flush()
    return draw


def auth_token(user_id, role="admin"):
    return create_access_token(str(user_id), role)


def cleanup(db, user_ids, tenant_ids):
    if tenant_ids:
        db.execute(delete(Lottery).where(Lottery.tenant_id.in_(tenant_ids)))
        db.execute(delete(Membership).where(Membership.tenant_id.in_(tenant_ids)))
        db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    if user_ids:
        db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def test_analytics_overview_isolated_between_tenants():
    db = SessionLocal()
    user_a = seed_user(db, "analytics-a")
    user_b = seed_user(db, "analytics-b")
    tenant_a = seed_tenant(db, "analytics-a")
    tenant_b = seed_tenant(db, "analytics-b")
    seed_membership(db, tenant_a.id, user_a.id)
    seed_membership(db, tenant_b.id, user_b.id)
    lottery_a = seed_lottery(db, tenant_a.id, "ANA")
    lottery_b = seed_lottery(db, tenant_b.id, "ANB")
    seed_draw(db, lottery_a.id, 1)
    seed_draw(db, lottery_a.id, 2)
    seed_draw(db, lottery_b.id, 3)
    user_a_id, user_b_id = user_a.id, user_b.id
    tenant_a_id, tenant_b_id = tenant_a.id, tenant_b.id
    db.commit()
    db.close()
    try:
        response_a = client.get(
            "/api/v1/statistics/overview",
            headers={"Authorization": f"Bearer {auth_token(user_a_id)}"},
        )
        response_b = client.get(
            "/api/v1/statistics/overview",
            headers={"Authorization": f"Bearer {auth_token(user_b_id)}"},
        )
        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert response_a.json()["draws_analyzed"] == 2
        assert response_b.json()["draws_analyzed"] == 1
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_a_id, user_b_id], [tenant_a_id, tenant_b_id])
        cleanup_db.close()


def test_analytics_cannot_select_other_tenant_with_header():
    db = SessionLocal()
    user = seed_user(db, "analytics-header")
    tenant_a = seed_tenant(db, "analytics-header-a")
    tenant_b = seed_tenant(db, "analytics-header-b")
    seed_membership(db, tenant_a.id, user.id)
    lottery_a = seed_lottery(db, tenant_a.id, "AH-A")
    lottery_b = seed_lottery(db, tenant_b.id, "AH-B")
    seed_draw(db, lottery_a.id, 11)
    seed_draw(db, lottery_b.id, 12)
    user_id, tenant_a_id, tenant_b_id = user.id, tenant_a.id, tenant_b.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/statistics/overview",
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


def test_analytics_requires_authorized_membership():
    db = SessionLocal()
    user = seed_user(db, "analytics-viewer")
    tenant = seed_tenant(db, "analytics-viewer")
    seed_membership(db, tenant.id, user.id, role="viewer")
    user_id, tenant_id = user.id, tenant.id
    db.commit()
    db.close()
    try:
        response = client.get(
            "/api/v1/statistics/overview",
            headers={"Authorization": f"Bearer {auth_token(user_id, 'viewer')}"},
        )
        assert response.status_code == 403
    finally:
        cleanup_db = SessionLocal()
        cleanup(cleanup_db, [user_id], [tenant_id])
        cleanup_db.close()


def test_analytics_route_uses_authenticated_tenant_context(monkeypatch):
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_tenant = app.dependency_overrides.get(get_tenant_context)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=901, role="admin", is_active=True
    )
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        user_id=901, tenant_id=902, membership_id=903, role="admin"
    )
    captured = {}

    def fake_overview(db, tenant_id):
        captured["tenant_id"] = tenant_id
        return {
            "module_status": "READY",
            "algorithms_count": 8,
            "draws_analyzed": 0,
        }

    monkeypatch.setattr(
        "app.api.routes.statistics.StatisticalService.overview", fake_overview
    )
    try:
        response = client.get("/api/v1/statistics/overview")
        assert response.status_code == 200
        assert captured["tenant_id"] == 902
    finally:
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user
        if previous_tenant is None:
            app.dependency_overrides.pop(get_tenant_context, None)
        else:
            app.dependency_overrides[get_tenant_context] = previous_tenant
