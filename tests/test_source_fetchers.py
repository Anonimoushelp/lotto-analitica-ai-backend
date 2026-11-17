import pytest
from httpx import MockTransport, Response

from app.sources.fetchers import (
    BalotoLatestResultFetcher,
    EmbeddedIframeSourceFetcher,
    HttpSourceFetcher,
    SourceFetchError,
)
from app.sources.parsers import BalotoResultPageParser


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



def test_embedded_iframe_fetcher_allows_explicit_cross_origin_official_host():
    def handler(request):
        if request.url.host == "rediapuestas.com" and request.url.path == "/resultados/":
            return Response(
                200,
                content=b'<html><body><iframe src="https://boletin.gana.com.co/"></iframe></body></html>',
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if request.url.host == "boletin.gana.com.co":
            return Response(
                200,
                content=b"<html><body>Sorteo 3174 Resultado 0166</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return Response(404, content=b"not found")

    fetcher = EmbeddedIframeSourceFetcher(
        allowed_hosts={"rediapuestas.com"},
        allowed_iframe_hosts={"boletin.gana.com.co"},
        transport=MockTransport(handler),
    )

    result = fetcher.fetch("https://rediapuestas.com/resultados/")

    assert result.status_code == 200
    assert result.url == "https://boletin.gana.com.co/"
    assert b"Resultado 0166" in result.content


def test_embedded_iframe_fetcher_tries_explicit_fallback_after_discovered_iframe_fails():
    def handler(request):
        if request.url.host == "rediapuestas.com" and request.url.path == "/resultados/":
            return Response(
                200,
                content=(
                    b'<html><body>'
                    b'<iframe class="resultados" src="https://boletin.gana.com.co/broken"></iframe>'
                    b'</body></html>'
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if request.url.host == "boletin.gana.com.co" and request.url.path == "/broken":
            return Response(503, content=b"temporarily unavailable")
        if request.url.host == "boletin.gana.com.co" and request.url.path == "/":
            return Response(
                200,
                content=b"<html><body>official iframe payload</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return Response(404, content=b"not found")

    fetcher = EmbeddedIframeSourceFetcher(
        allowed_hosts={"rediapuestas.com"},
        allowed_iframe_hosts={"boletin.gana.com.co"},
        fallback_iframe_urls=("https://boletin.gana.com.co/",),
        transport=MockTransport(handler),
    )

    result = fetcher.fetch("https://rediapuestas.com/resultados/")

    assert result.url == "https://boletin.gana.com.co/"
    assert b"official iframe payload" in result.content


@pytest.mark.parametrize(
    ("draw_type", "detail_path", "numbers", "bonus_key", "expected_bonus"),
    [
        (
            "BALOTO",
            "/resultados-baloto/2736",
            "02 12 19 25 42 07",
            "superbalota",
            [7],
        ),
        (
            "REVANCHA",
            "/resultados-revancha/2736",
            "02 17 27 33 37 10",
            "revancha_bonus",
            [10],
        ),
    ],
)
def test_baloto_latest_fetcher_resolves_the_matching_official_detail_page(
    draw_type,
    detail_path,
    numbers,
    bonus_key,
    expected_bonus,
):
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/resultados":
            return Response(
                200,
                content=(
                    b'<a href="/resultados-baloto/2736">Ver detalle</a>'
                    b'<a href="/resultados-revancha/2736">Ver detalle</a>'
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if request.url.path == detail_path:
            detail_html = (
                "<html><body>"
                "<div>SORTEO 2.736</div>"
                "<div>16 de Noviembre de 2026</div>"
                "<div>MIRA EL VIDEO OFICIAL DEL SORTEO</div>"
                f"<div>{numbers}</div>"
                "<div>TOTAL GANADORES</div>"
                "</body></html>"
            ).encode("utf-8")
            return Response(
                200,
                content=detail_html,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return Response(404, content=b"not found")

    fetcher = BalotoLatestResultFetcher(
        draw_type=draw_type,
        transport=MockTransport(handler),
    )
    fetched = fetcher.fetch("https://www.baloto.com/resultados")
    payload = next(iter(BalotoResultPageParser(draw_type=draw_type).parse(fetched)))

    assert fetched.url == f"https://www.baloto.com{detail_path}"
    assert payload["draw_number"] == "2736"
    assert payload["draw_date"] == "2026-11-16"
    assert payload["main_numbers"] == [2, 12, 19, 25, 42]
    assert payload[bonus_key] == expected_bonus
    assert requests == ["/resultados", detail_path]


def test_baloto_latest_fetcher_rejects_an_index_without_the_requested_game():
    def handler(request):
        return Response(
            200,
            content=b'<a href="/resultados-baloto/2736">Ver detalle</a>',
            headers={"content-type": "text/html; charset=utf-8"},
        )

    fetcher = BalotoLatestResultFetcher(
        draw_type="REVANCHA",
        transport=MockTransport(handler),
    )

    with pytest.raises(
        SourceFetchError, match="missing the latest REVANCHA detail link"
    ):
        fetcher.fetch("https://www.baloto.com/resultados")
