import pytest
from fastapi import HTTPException

from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import require_tenant_scopes


def make_dependency(role: str):
    dependency = require_tenant_scopes("lotteries:read")
    tenant = TenantContext(
        user_id=1,
        tenant_id=1,
        membership_id=1,
        role=role,
    )
    return dependency, tenant


def test_admin_can_use_read_scope():
    dependency, tenant = make_dependency("admin")
    assert dependency.__closure__[0].cell_contents is not None
    assert tenant.role == "admin"


def test_analyst_can_use_read_scope():
    dependency, tenant = make_dependency("analyst")
    assert dependency.__closure__[0].cell_contents is not None
    assert tenant.role == "analyst"


def test_viewer_is_denied_read_scope():
    dependency = require_tenant_scopes("lotteries:read")
    tenant = TenantContext(user_id=1, tenant_id=1, membership_id=1, role="viewer")
    with pytest.raises(HTTPException) as exc_info:
        dependency.__closure__[0].cell_contents(tenant)
    assert exc_info.value.status_code == 403


def test_service_is_denied_read_scope():
    dependency = require_tenant_scopes("lotteries:read")
    tenant = TenantContext(user_id=1, tenant_id=1, membership_id=1, role="service")
    with pytest.raises(HTTPException) as exc_info:
        dependency.__closure__[0].cell_contents(tenant)
    assert exc_info.value.status_code == 403


def test_unknown_role_is_denied():
    dependency = require_tenant_scopes("lotteries:read")
    tenant = TenantContext(user_id=1, tenant_id=1, membership_id=1, role="unknown")
    with pytest.raises(HTTPException) as exc_info:
        dependency.__closure__[0].cell_contents(tenant)
    assert exc_info.value.status_code == 403


def test_multiple_scopes_use_and_semantics():
    dependency = require_tenant_scopes("lotteries:read", "lotteries:write")
    tenant = TenantContext(user_id=1, tenant_id=1, membership_id=1, role="analyst")
    with pytest.raises(HTTPException) as exc_info:
        dependency.__closure__[0].cell_contents(tenant)
    assert exc_info.value.status_code == 403
