from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.api.dependencies.tenant import TenantContext, get_tenant_context


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


require_tenant_admin = require_tenant_roles("admin")
require_tenant_admin_or_analyst = require_tenant_roles("admin", "analyst")
