from httpx import MockTransport, Response
import pytest

from app.sources.fetchers import HttpSourceFetcher, SourceFetchError


def test_http_fetcher_requires_https():
    fetcher = HttpSourceFetcher()
    with pytest.raises(SourceFetchError, match="HTTPS"):
        fetcher.fetch("http://example.test/results")


def test_http_fetcher_enforces_host_allowlist():
    fetcher = HttpSourceFetcher(allowed_hosts={"official.example"})
    with pytest.raises(SourceFetchError, match="allowlisted"):
        fetcher.fetch("https://other.example/results")


def test_http_fetcher_rejects_url_credentials():
    fetcher = HttpSourceFetcher()
    with pytest.raises(SourceFetchError, match="credentials"):
        fetcher.fetch("https://user:pass@example.test/results")


def test_http_fetcher_rejects_oversized_response():
    transport = MockTransport(lambda request: Response(200, content=b"123456"))
    fetcher = HttpSourceFetcher(
        allowed_hosts={"example.test"},
        max_response_bytes=5,
        transport=transport,
    )
    with pytest.raises(SourceFetchError, match="size limit"):
        fetcher.fetch("https://example.test/results")


def test_http_fetcher_preserves_fetch_metadata():
    transport = MockTransport(
        lambda request: Response(
            200,
            content=b'{"results": []}',
            headers={"content-type": "application/json"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={"example.test"},
        transport=transport,
    )

    result = fetcher.fetch("https://example.test/results")

    assert result.status_code == 200
    assert result.url == "https://example.test/results"
    assert result.content == b'{"results": []}'
    assert result.content_type == "application/json"
    assert result.fetched_at is not None
