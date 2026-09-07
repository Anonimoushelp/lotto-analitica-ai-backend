from fastapi import HTTPException

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import (
    require_tenant_admin,
    require_tenant_admin_or_analyst,
)


def test_membership_role_is_authoritative_for_admin_access():
    tenant = TenantContext(user_id=1, tenant_id=10, membership_id=100, role="viewer")

    try:
        require_tenant_admin(tenant)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("viewer membership must not receive admin access")


def test_analyst_membership_can_read_but_not_mutate():
    tenant = TenantContext(user_id=1, tenant_id=10, membership_id=100, role="analyst")

    assert require_tenant_admin_or_analyst(tenant) is tenant

    try:
        require_tenant_admin(tenant)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("analyst membership must not receive admin access")


def test_admin_membership_receives_admin_access():
    tenant = TenantContext(user_id=1, tenant_id=10, membership_id=100, role="admin")

    assert require_tenant_admin(tenant) is tenant
