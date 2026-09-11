from fastapi.testclient import TestClient

from app.api.dependencies.tenant import TenantContext, get_tenant_context
from app.main import app


def _authorized_tenant():
    return TenantContext(user_id=1, tenant_id=1, membership_id=1, role="analyst")


def test_tee_status_requires_authentication():
    response = TestClient(app).get("/api/v1/tee/status")
    assert response.status_code == 401


def test_tee_status_is_fail_closed_without_provider():
    app.dependency_overrides[get_tenant_context] = _authorized_tenant
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


def test_tee_operation_requires_authentication():
    response = TestClient(app).post(
        "/api/v1/tee/operations",
        json={"operation": "attest", "nonce": "0123456789abcdef"},
    )
    assert response.status_code == 401


def test_tee_operation_fails_closed_without_provider():
    app.dependency_overrides[get_tenant_context] = _authorized_tenant
    try:
        response = TestClient(app).post(
            "/api/v1/tee/operations",
            json={"operation": "attest", "nonce": "0123456789abcdef"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "TEE attestation provider unavailable"}


def test_tee_operation_rejects_unknown_fields():
    app.dependency_overrides[get_tenant_context] = _authorized_tenant
    try:
        response = TestClient(app).post(
            "/api/v1/tee/operations",
            json={
                "operation": "attest",
                "nonce": "0123456789abcdef",
                "attestation": "synthetic",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
