import json

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.gemini_client import GeminiClient


class MockResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class MockClient:
    response = None
    last_request = None

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, headers, json):
        type(self).last_request = {"url": url, "headers": headers, "body": json}
        return self.response


def test_gemini_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(HTTPException) as exc_info:
        GeminiClient.generate_json("test prompt")

    assert exc_info.value.status_code == 503
    assert "not configured" in str(exc_info.value.detail)


def test_gemini_client_maps_timeout_to_504(monkeypatch):
    class TimeoutClient(MockClient):
        def post(self, url, *, headers, json):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.gemini_client.httpx.Client", TimeoutClient)

    with pytest.raises(HTTPException) as exc_info:
        GeminiClient.generate_json("test prompt")

    assert exc_info.value.status_code == 504


def test_gemini_client_maps_transport_error_to_502(monkeypatch):
    class TransportErrorClient(MockClient):
        def post(self, url, *, headers, json):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.gemini_client.httpx.Client", TransportErrorClient)

    with pytest.raises(HTTPException) as exc_info:
        GeminiClient.generate_json("test prompt")

    assert exc_info.value.status_code == 502


def test_gemini_client_maps_http_error_to_502(monkeypatch):
    request = httpx.Request("POST", GeminiClient.API_URL)
    MockClient.response = MockResponse(
        error=httpx.HTTPStatusError(
            "bad gateway",
            request=request,
            response=httpx.Response(500, request=request),
        )
    )

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.gemini_client.httpx.Client", MockClient)

    with pytest.raises(HTTPException) as exc_info:
        GeminiClient.generate_json("test prompt")

    assert exc_info.value.status_code == 502


def test_gemini_client_rejects_malformed_response(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]}
    MockClient.response = MockResponse(payload=payload)

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.gemini_client.httpx.Client", MockClient)

    with pytest.raises(HTTPException) as exc_info:
        GeminiClient.generate_json("test prompt")

    assert exc_info.value.status_code == 502
    assert "invalid structured response" in str(exc_info.value.detail)


def test_gemini_client_rejects_non_dict_response(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": json.dumps([])}]}}]}
    MockClient.response = MockResponse(payload=payload)

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.gemini_client.httpx.Client", MockClient)

    with pytest.raises(HTTPException) as exc_info:
        GeminiClient.generate_json("test prompt")

    assert exc_info.value.status_code == 502
    assert "invalid response shape" in str(exc_info.value.detail)


def test_gemini_client_keeps_api_key_out_of_url_and_body(monkeypatch):
    secret = "super-secret-gemini-key"
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps({"predictions": []})}]}}
        ]
    }
    MockClient.response = MockResponse(payload=payload)

    monkeypatch.setattr(settings, "gemini_api_key", secret)
    monkeypatch.setattr("app.services.gemini_client.httpx.Client", MockClient)

    result = GeminiClient.generate_json("historical lottery prompt", temperature=0.7)
    request = MockClient.last_request

    assert result == {"predictions": []}
    assert secret not in request["url"]
    assert secret not in json.dumps(request["body"])
    assert request["headers"]["x-goog-api-key"] == secret
    assert request["body"]["generationConfig"] == {
        "temperature": 0.7,
        "responseMimeType": "application/json",
    }
