from __future__ import annotations

import httpx
import pytest

from app.sources.fetchers import RisaraldaOfficialSourceFetcher, SourceFetchError
from app.sources.provider_registry import build_traditional_lottery_components


def test_risaralda_official_fetcher_combines_institutional_pages():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"2968+ Sorteos jugados",
                request=request,
            )
        if request.url.path == "/loteriaconsulta/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"PREMIO MAYOR 6731 Serie 197",
                request=request,
            )
        return httpx.Response(404, request=request)

    fetcher = RisaraldaOfficialSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    result = fetcher.fetch("https://loteriadelrisaralda.com/")

    assert result.status_code == 200
    assert result.url == "https://loteriadelrisaralda.com/"
    assert b"2968+ Sorteos jugados" in result.content
    assert b"RISARALDA_OFFICIAL_CONSULTATION" in result.content
    assert b"PREMIO MAYOR 6731 Serie 197" in result.content
    assert calls == [
        "https://loteriadelrisaralda.com/",
        "https://loteriadelrisaralda.com/loteriaconsulta/",
    ]



def test_risaralda_sales_portal_fetcher_parses_official_major_result():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "ventas.loteriadelrisaralda.com":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=(
                    b"<html><body>"
                    b"<h1>Resultados de la Loteria</h1>"
                    b"<p>Sorteo No. 2975</p>"
                    b"<p>viernes, 13 de noviembre de 2026</p>"
                    b"<h2>Premio mayor</h2>"
                    b"<span>8</span><span>3</span><span>6</span><span>2</span>"
                    b"<p>Serie 118</p>"
                    b"</body></html>"
                ),
                request=request,
            )
        return httpx.Response(404, request=request)

    fetcher = RisaraldaOfficialSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    result = fetcher.fetch("https://ventas.loteriadelrisaralda.com/resultados")
    parser, adapter = build_traditional_lottery_components("LOTERIA_RISARALDA")

    records = list(parser.parse(result))
    normalized = adapter.normalize(records[0])

    assert calls == ["https://ventas.loteriadelrisaralda.com/resultados"]
    assert normalized.draw_number == "2975"
    assert normalized.draw_date.isoformat() == "2026-11-13"
    assert normalized.main_numbers == [8362]
    assert normalized.metadata["series"] == "118"
    assert normalized.metadata["date_inferred_from_draw_schedule"] is False
    assert normalized.metadata["source_format"] == "official_sales_portal_result"
    assert normalized.source_url == "https://ventas.loteriadelrisaralda.com/resultados"


def test_risaralda_sales_portal_javascript_shell_uses_official_fallback():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "ventas.loteriadelrisaralda.com":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"<html><body><div id='app'></div><script>hydrate()</script></body></html>",
                request=request,
            )
        if request.url.host == "loteriadelrisaralda.com" and request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"<html><body>2976+ Sorteos jugados</body></html>",
                request=request,
            )
        if request.url.host == "loteriadelrisaralda.com" and request.url.path == "/loteriaconsulta/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=(
                    b"<html><body>"
                    b"Sorteo No. 2975 viernes, 13 de noviembre de 2026 "
                    b"Premio mayor 8362 Serie 118"
                    b"</body></html>"
                ),
                request=request,
            )
        return httpx.Response(404, request=request)

    fetcher = RisaraldaOfficialSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    result = fetcher.fetch("https://ventas.loteriadelrisaralda.com/resultados")
    parser, adapter = build_traditional_lottery_components("LOTERIA_RISARALDA")

    records = list(parser.parse(result))
    normalized = adapter.normalize(records[0])

    assert calls == [
        "https://ventas.loteriadelrisaralda.com/resultados",
        "https://loteriadelrisaralda.com/",
        "https://loteriadelrisaralda.com/loteriaconsulta/",
    ]
    assert normalized.draw_number == "2975"
    assert normalized.draw_date.isoformat() == "2026-11-13"
    assert normalized.main_numbers == [8362]
    assert normalized.metadata["series"] == "118"


def test_risaralda_strict_live_mode_returns_javascript_shell_without_fallback():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><body><div id='app'></div><script>hydrate()</script></body></html>",
            request=request,
        )

    fetcher = RisaraldaOfficialSourceFetcher(
        allowed_hosts={"ventas.loteriadelrisaralda.com"},
        allow_institutional_fallback=False,
        follow_redirects=False,
        transport=httpx.MockTransport(handler),
    )
    result = fetcher.fetch("https://ventas.loteriadelrisaralda.com/resultados")

    assert result.status_code == 200
    assert b"id='app'" in result.content
    assert calls == ["https://ventas.loteriadelrisaralda.com/resultados"]


def test_risaralda_strict_live_mode_does_not_follow_official_portal_redirects():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://loteriadelrisaralda.com/"},
            request=request,
        )

    fetcher = RisaraldaOfficialSourceFetcher(
        allowed_hosts={"ventas.loteriadelrisaralda.com"},
        allow_institutional_fallback=False,
        follow_redirects=False,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SourceFetchError):
        fetcher.fetch("https://ventas.loteriadelrisaralda.com/resultados")

    assert calls == ["https://ventas.loteriadelrisaralda.com/resultados"]
