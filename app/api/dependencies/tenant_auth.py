from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.api.dependencies.tenant import TenantContext, get_tenant_context
from app.core.permissions import Scope, has_scope


def require_tenant_roles(*allowed_roles: str) -> Callable:
    def dependency(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if tenant.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return tenant

    return dependency


def require_tenant_scopes(*required_scopes: Scope) -> Callable:
    def dependency(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if not all(has_scope(tenant.role, scope) for scope in required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return tenant

    return dependency


require_tenant_admin = require_tenant_roles("admin")
require_tenant_admin_or_analyst = require_tenant_roles("admin", "analyst")
require_lotteries_read = require_tenant_scopes("lotteries:read")
require_lotteries_write = require_tenant_scopes("lotteries:write")
require_draws_read = require_tenant_scopes("draws:read")
require_draws_write = require_tenant_scopes("draws:write")
