import pytest
from httpx import MockTransport, Response

from app.sources.fetchers import (
    EmbeddedIframeSourceFetcher,
    HttpSourceFetcher,
    SourceFetchError,
)


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


def test_embedded_iframe_fetcher_follows_same_origin_result_frame():
    def handler(request):
        if request.url.path == "/":
            return Response(
                200,
                content=(
                    b'<html><body>'
                    b'<iframe src="https://other.example/track"></iframe>'
                    b'<iframe class="resultados" src="/resultado-actual"></iframe>'
                    b'</body></html>'
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if request.url.path == "/resultado-actual":
            return Response(
                200,
                content=b"<html><body>Sorteo 4821 Resultado 5341</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return Response(404, content=b"not found")

    fetcher = EmbeddedIframeSourceFetcher(
        allowed_hosts={"example.test"},
        transport=MockTransport(handler),
    )

    result = fetcher.fetch("https://example.test/")

    assert result.status_code == 200
    assert result.url == "https://example.test/resultado-actual"
    assert b"Sorteo 4821" in result.content
