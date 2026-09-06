from fastapi.testclient import TestClient

from app.api.dependencies.auth import require_admin_or_analyst
from app.main import app


def test_tee_status_requires_authentication():
    response = TestClient(app).get("/api/v1/tee/status")
    assert response.status_code == 401


def test_tee_status_is_fail_closed_without_provider():
    app.dependency_overrides[require_admin_or_analyst] = lambda: object()
    try:
        response = TestClient(app).get("/api/v1/tee/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "module": "M67",
        "capability": "trusted_execution_environment",
        "status": "integration_pending",
        "production_ready": False,
        "confidential_compute_backend_connected": False,
        "provider": "none",
        "attestation_available": False,
        "message": "No verified TEE provider is connected",
    }
