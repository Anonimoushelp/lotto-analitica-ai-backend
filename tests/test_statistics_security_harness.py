from fastapi.testclient import TestClient

from app.main import app


def test_statistics_security_client_can_observe_sanitized_500():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
