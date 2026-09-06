from fastapi.testclient import TestClient

from app.api.dependencies.auth import require_admin_or_analyst
from app.main import app

client = TestClient(app)


def test_functional_encryption_status_requires_authentication():
    response = client.get("/api/v1/functional-encryption/status")
    assert response.status_code == 401


def test_functional_encryption_status_is_fail_closed_without_provider():
    app.dependency_overrides[require_admin_or_analyst] = lambda: object()
    try:
        response = client.get("/api/v1/functional-encryption/status")
        assert response.status_code == 200
        assert response.json() == {
            "module": "M66",
            "capability": "functional_encryption",
            "status": "integration_pending",
            "production_ready": False,
            "cryptographic_backend_connected": False,
            "provider": "none",
            "message": "No verified Functional Encryption provider is installed",
        }
    finally:
        app.dependency_overrides.clear()


def test_functional_encryption_operation_requires_authentication():
    response = client.post(
        "/api/v1/functional-encryption/operations",
        json={"operation": "encrypt", "payload": {"value": "test"}},
    )
    assert response.status_code == 401


def test_functional_encryption_operation_rejects_unknown_fields():
    app.dependency_overrides[require_admin_or_analyst] = lambda: object()
    try:
        response = client.post(
            "/api/v1/functional-encryption/operations",
            json={"operation": "encrypt", "payload": {}, "unexpected": True},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_functional_encryption_operation_fails_closed_without_provider():
    app.dependency_overrides[require_admin_or_analyst] = lambda: object()
    try:
        response = client.post(
            "/api/v1/functional-encryption/operations",
            json={"operation": "evaluate", "payload": {"ciphertext": "opaque"}},
        )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Functional Encryption provider is unavailable"
        }
    finally:
        app.dependency_overrides.clear()
