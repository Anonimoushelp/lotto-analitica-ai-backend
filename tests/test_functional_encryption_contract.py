from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_functional_encryption_status_requires_authentication():
    response = client.get("/api/v1/functional-encryption/status")
    assert response.status_code == 401


def test_functional_encryption_status_contract(monkeypatch):
    from app.api.dependencies.auth import get_current_user
    from app.models.user import User

    user = User(id=1, email="analyst@example.com", role="analyst", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
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
