from fastapi.testclient import TestClient

from app.main import MAX_REQUEST_BODY_BYTES, app


client = TestClient(app)


def test_request_body_size_limit_rejects_oversized_declared_payload():
    response = client.post(
        "/api/v1/predictions",
        headers={"Content-Length": str(MAX_REQUEST_BODY_BYTES + 1)},
        content=b"{}",
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_request_body_size_limit_accepts_payload_within_declared_limit():
    response = client.post(
        "/api/v1/predictions",
        headers={"Content-Length": str(MAX_REQUEST_BODY_BYTES)},
        content=b"{}",
    )

    assert response.status_code == 401


def test_request_body_size_limit_rejects_negative_content_length():
    response = client.post(
        "/api/v1/predictions",
        headers={"Content-Length": "-1"},
        content=b"{}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Content-Length header"}
