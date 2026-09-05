import logging

import pytest
from fastapi import Request

from app.main import unhandled_exception_handler


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500_without_sensitive_details(caplog):
    secret = "super-secret-api-key"
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/internal-error",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
    }
    request = Request(scope)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = await unhandled_exception_handler(
            request,
            RuntimeError(secret),
        )

    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal server error"}'
    assert secret not in response.body.decode()
    assert secret not in caplog.text
    assert "Internal server error" not in caplog.text


def test_unhandled_exception_handler_is_registered_on_application():
    from app.main import app

    assert Exception in app.exception_handlers
    assert app.exception_handlers[Exception] is unhandled_exception_handler
