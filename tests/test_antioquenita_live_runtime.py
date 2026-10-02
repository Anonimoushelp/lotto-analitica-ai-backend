import re
from urllib.parse import urlparse

import httpx
import pytest

from app.sources.fetchers import EmbeddedIframeSourceFetcher
from app.sources.four_digit_parsers import AntioquenitaHtmlParser


@pytest.mark.integration
def test_antioquenita_live_official_iframe_runtime():
    fetcher = EmbeddedIframeSourceFetcher(
        timeout=30.0,
        allowed_iframe_hosts={"boletin.gana.com.co"},
        fallback_iframe_urls=("https://boletin.gana.com.co/",),
    )

    result = fetcher.fetch("https://rediapuestas.com/resultados/")

    assert 200 <= result.status_code < 300
    assert urlparse(result.url).hostname == "boletin.gana.com.co"

    gana_response = httpx.get(
        "https://www.gana.com.co/lista-resultados/",
        timeout=20.0,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )
    gana_html = gana_response.text
    print(
        "ANTIOQUENITA_GANA_RESULTS_META",
        gana_response.status_code,
        gana_response.headers.get("content-type"),
        len(gana_response.content),
        gana_response.url,
    )
    print(
        "ANTIOQUENITA_GANA_IFRAMES",
        re.findall(r'''<iframe[^>]+(?:src|data-src)\\s*=\\s*["']([^"']+)["']''', gana_html, flags=re.I),
    )
    print(
        "ANTIOQUENITA_GANA_SCRIPTS",
        re.findall(r'''<script[^>]+src=["']([^"']+)["']''', gana_html, flags=re.I)[:100],
    )
    print("ANTIOQUENITA_GANA_HEAD", gana_html[:12000])

    html = result.content.decode("utf-8", errors="replace")
    print(
        "\nANTIOQUENITA_SOURCE_META "
        f"status={result.status_code} content_type={result.content_type!r} "
        f"bytes={len(result.content)} url={result.url}"
    )
    print(
        "ANTIOQUENITA_SCRIPT_SRCS",
        re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I),
    )
    print("ANTIOQUENITA_HTML_BEGIN")
    print(html[:20000])
    print("ANTIOQUENITA_HTML_END")

    script_srcs = re.findall(
        r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I
    )
    for script_src in script_srcs:
        script_url = (
            f"https://boletin.gana.com.co{script_src}"
            if script_src.startswith("/")
            else script_src
        )
        request_headers = [
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/javascript,*/*;q=0.1",
                "Referer": "https://boletin.gana.com.co/",
                "Sec-Fetch-Dest": "script",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
            },
        ]
        script_response = None
        for headers in request_headers:
            candidate = httpx.get(script_url, timeout=30.0, headers=headers)
            print(
                "ANTIOQUENITA_SCRIPT_META",
                candidate.status_code,
                candidate.headers.get("content-type"),
                script_url,
                len(candidate.content),
                headers.get("Accept"),
            )
            script_response = candidate
            if "javascript" in candidate.headers.get("content-type", "").casefold():
                break
        assert script_response is not None
        if "javascript" in script_response.headers.get("content-type", "").casefold():
            script_text = script_response.text
            print(
                "ANTIOQUENITA_API_HINTS",
                re.findall(
                    r"https?://[^\s\"']+|/[^\s\"']*(?:api|result|sorte|ganador)[^\s\"']*",
                    script_text,
                    flags=re.I,
                )[:200],
            )
            print("ANTIOQUENITA_SCRIPT_HEAD", script_text[:4000])
        else:
            print("ANTIOQUENITA_SCRIPT_HEAD", script_response.text[:4000])

    base_requests = (
        ("https://backend-boletin.gana-web.com", {}),
        ("https://backend-keno.gana-web.com", {}),
        (
            "http://18.221.39.113",
            {"Host": "backend-boletin.gana-web.com"},
        ),
    )
    for base_url, host_headers in base_requests:
        for path in (
            "/",
            "/openapi.json",
            "/swagger/index.html",
            "/swagger/v1/swagger.json",
            "/api",
            "/api/resultados",
            "/api/resultados/",
            "/api/result",
            "/api/results",
            "/api/sorteos",
            "/api/resultado",
            "/api/lotteries",
            "/api/v1/resultados",
            "/api/v1/results",
            "/api/v1/sorteos",
            "/resultados",
            "/resultados/",
        ):
            endpoint = base_url + path
            try:
                probe = httpx.get(
                    endpoint,
                    timeout=5.0,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json,text/plain,*/*",
                        "Referer": "https://boletin.gana.com.co/",
                        **host_headers,
                    },
                )
                print(
                    "ANTIOQUENITA_API_PROBE",
                    probe.status_code,
                    probe.headers.get("content-type"),
                    endpoint,
                    len(probe.content),
                    probe.text[:300].replace("\n", " "),
                )
            except httpx.HTTPError as exc:
                print("ANTIOQUENITA_API_PROBE_ERROR", endpoint, repr(exc))

    records = list(AntioquenitaHtmlParser().parse(result))

    assert records, "The official Antioqueñita iframe returned no parseable records"
    assert {record["draw_type"] for record in records} <= {
        "ANTIOQUENITA_1",
        "ANTIOQUENITA_2",
    }
    for record in records:
        assert str(record["draw_number"]).isdigit()
        assert str(record["draw_date"])
        assert str(record["number"]).isdigit()
        assert len(str(record["number"])) == 4


@pytest.mark.integration
def test_antioquenita_public_backend_endpoint_discovery():
    base_urls = (
        "https://backend-boletin.gana-web.com",
        "https://backend-keno.gana-web.com",
    )
    paths = (
        "/",
        "/openapi.json",
        "/swagger/index.html",
        "/swagger/v1/swagger.json",
        "/api",
        "/api/resultados",
        "/api/resultados/",
        "/api/result",
        "/api/results",
        "/api/sorteos",
        "/api/resultado",
        "/api/lotteries",
        "/api/v1/resultados",
        "/api/v1/results",
        "/api/v1/sorteos",
    )
    found = []
    for base_url in base_urls:
        for path in paths:
            try:
                response = httpx.get(
                    base_url + path,
                    timeout=10.0,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json,text/plain,*/*",
                    },
                )
            except httpx.HTTPError as exc:
                print("ANTIOQUENITA_API_PROBE_ERROR", base_url + path, repr(exc))
                continue
            content_type = response.headers.get("content-type", "")
            preview = response.text[:500].replace("\n", " ")
            print(
                "ANTIOQUENITA_API_PROBE",
                response.status_code,
                content_type,
                base_url + path,
                len(response.content),
                preview,
            )
            if response.status_code < 500 and (
                "json" in content_type.casefold()
                or "sorte" in response.text.casefold()
                or "antioquen" in response.text.casefold()
            ):
                found.append((base_url + path, response.status_code, content_type))
    print("ANTIOQUENITA_API_PROBE_FOUND", found)
