from fastapi.middleware.cors import CORSMiddleware

from app.main import app


def test_cors_allows_tenant_selection_header() -> None:
    cors_middlewares = [
        middleware
        for middleware in app.user_middleware
        if middleware.cls is CORSMiddleware
    ]

    assert cors_middlewares, "CORS middleware must be configured"
    assert "X-Tenant-ID" in cors_middlewares[0].kwargs["allow_headers"]
