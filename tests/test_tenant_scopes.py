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
    assert dependency(tenant) == tenant


def test_analyst_can_use_read_scope():
    dependency, tenant = make_dependency("analyst")
    assert dependency(tenant) == tenant


def test_viewer_is_denied_read_scope():
    dependency, tenant = make_dependency("viewer")
    with pytest.raises(HTTPException) as exc_info:
        dependency(tenant)
    assert exc_info.value.status_code == 403


def test_service_is_denied_read_scope():
    dependency, tenant = make_dependency("service")
    with pytest.raises(HTTPException) as exc_info:
        dependency(tenant)
    assert exc_info.value.status_code == 403


def test_unknown_role_is_denied():
    dependency, tenant = make_dependency("unknown")
    with pytest.raises(HTTPException) as exc_info:
        dependency(tenant)
    assert exc_info.value.status_code == 403


def test_multiple_scopes_use_and_semantics():
    dependency = require_tenant_scopes("lotteries:read", "lotteries:write")
    tenant = TenantContext(user_id=1, tenant_id=1, membership_id=1, role="analyst")
    with pytest.raises(HTTPException) as exc_info:
        dependency(tenant)
    assert exc_info.value.status_code == 403
