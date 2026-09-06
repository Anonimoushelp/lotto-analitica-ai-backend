from fastapi.testclient import TestClient

from app.api.dependencies.auth import require_admin_or_analyst
from app.main import app

client = TestClient(app)


def test_functional_encryption_status_requires_authentication():
    response = client.get("/api/v1/functional-encryption/status")
    assert response.status_code == 401


def test_functional_encryption_status_contract():
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
            "message": "Functional Encryption backend integration is pending",
        }
    finally:
        app.dependency_overrides.clear()
