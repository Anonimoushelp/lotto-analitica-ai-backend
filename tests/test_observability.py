import logging

from fastapi.testclient import TestClient

from app.main import REQUEST_ID_HEADER, app

client = TestClient(app)


def test_request_observability_generates_and_returns_request_id(caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get("/")

    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    assert "request_completed" in caplog.text
    assert request_id in caplog.text
    assert "method=GET" in caplog.text
    assert "path=/" in caplog.text
    assert "status_code=200" in caplog.text


def test_request_observability_preserves_supplied_request_id(caplog):
    request_id = "trace-test-123"
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get("/", headers={REQUEST_ID_HEADER: request_id})

    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert request_id in caplog.text
