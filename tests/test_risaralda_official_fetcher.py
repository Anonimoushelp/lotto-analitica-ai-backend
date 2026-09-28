from __future__ import annotations

import httpx

from app.sources.fetchers import RisaraldaOfficialSourceFetcher


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
