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
        "ANTIOQUENITA_GANA_SCRIPTS",
        re.findall(
            r'''<script[^>]+src=["']([^"']+)["']''',
            gana_html,
            flags=re.I,
        ),
    )
    print("ANTIOQUENITA_GANA_HEAD", gana_html[:6000])

    html = result.content.decode("utf-8", errors="replace")
    script_srcs = re.findall(
        r'''<script[^>]+src=["']([^"']+)["']''',
        html,
        flags=re.I,
    )
    print("ANTIOQUENITA_IFRAME_HTML", html[:6000])

    for script_src in script_srcs:
        if not script_src.startswith("/"):
            continue
        script_url = f"https://boletin.gana.com.co{script_src}"
        candidate = httpx.get(
            script_url,
            timeout=15.0,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/javascript,*/*;q=0.1",
                "Referer": "https://boletin.gana.com.co/",
                "Sec-Fetch-Dest": "script",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        print(
            "ANTIOQUENITA_SCRIPT_META",
            candidate.status_code,
            candidate.headers.get("content-type"),
            script_url,
            len(candidate.content),
        )
        print("ANTIOQUENITA_SCRIPT_HEAD", candidate.text[:2500])

    backend_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://boletin.gana.com.co/",
        "Origin": "https://boletin.gana.com.co",
        "Host": "backend-boletin.gana-web.com",
    }
    for path in (
        "/",
        "/admin",
        "/admin/",
        "/admin/login",
        "/health",
        "/healthz",
        "/status",
        "/graphql",
        "/api",
        "/api/resultados",
        "/api/results",
        "/api/sorteos",
        "/api/resultado",
        "/api/v1/resultados",
    ):
        try:
            probe = httpx.get(
                f"http://18.221.39.113{path}",
                timeout=8.0,
                headers=backend_headers,
            )
        except httpx.HTTPError as exc:
            print("ANTIOQUENITA_BACKEND_ERROR", path, repr(exc))
            continue
        print(
            "ANTIOQUENITA_BACKEND",
            probe.status_code,
            probe.headers.get("content-type"),
            path,
            len(probe.content),
            probe.text[:2500].replace("\n", " "),
        )

    graphql_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://boletin.gana.com.co/",
        "Origin": "https://boletin.gana.com.co",
        "Host": "backend-boletin.gana-web.com",
    }
    introspection_query = """
    {
      __schema {
        queryType {
          fields {
            name
            args {
              name
              type {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    graphql_response = httpx.post(
        "http://18.221.39.113/graphql",
        json={"query": introspection_query},
        timeout=15.0,
        headers=graphql_headers,
    )
    print(
        "ANTIOQUENITA_GRAPHQL_SCHEMA",
        graphql_response.status_code,
        graphql_response.headers.get("content-type"),
    )
    print("ANTIOQUENITA_GRAPHQL_BODY", graphql_response.text[:20000])

    type_query = """
    {
      __type(name: "Boletin_resultados") {
        fields {
          name
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
    """
    type_response = httpx.post(
        "http://18.221.39.113/graphql",
        json={"query": type_query},
        timeout=15.0,
        headers=graphql_headers,
    )
    print("ANTIOQUENITA_GRAPHQL_TYPE", type_response.status_code)
    print("ANTIOQUENITA_GRAPHQL_TYPE_BODY", type_response.text[:20000])

    sample_query = """
    {
      Boletin_resultados(limit: 10, sort: ["-id"]) {
        id
      }
    }
    """
    sample_response = httpx.post(
        "http://18.221.39.113/graphql",
        json={"query": sample_query},
        timeout=15.0,
        headers=graphql_headers,
    )
    print("ANTIOQUENITA_GRAPHQL_SAMPLE_ID", sample_response.status_code)
    print("ANTIOQUENITA_GRAPHQL_SAMPLE_ID_BODY", sample_response.text[:12000])

    results_query = """
    {
      Boletin_resultados(limit: 50, sort: ["-date_created"]) {
        id
        status
        date_created
        date_updated
        Nombre_Sorteo
        logo {
          id
          filename_download
        }
      }
    }
    """
    results_response = httpx.post(
        "http://18.221.39.113/graphql",
        json={"query": results_query},
        timeout=15.0,
        headers=graphql_headers,
    )
    print("ANTIOQUENITA_GRAPHQL_RESULTS", results_response.status_code)
    print("ANTIOQUENITA_GRAPHQL_RESULTS_BODY", results_response.text[:30000])

    types_query = """
    {
      __schema {
        types {
          name
          kind
          fields {
            name
          }
        }
      }
    }
    """
    types_response = httpx.post(
        "http://18.221.39.113/graphql",
        json={"query": types_query},
        timeout=15.0,
        headers=graphql_headers,
    )
    print("ANTIOQUENITA_GRAPHQL_TYPES", types_response.status_code)
    try:
        type_rows = types_response.json()["data"]["__schema"]["types"]
        candidates = [
            {
                "name": row.get("name"),
                "kind": row.get("kind"),
                "fields": [field.get("name") for field in (row.get("fields") or [])],
            }
            for row in type_rows
            if any(
                token in (row.get("name") or "").casefold()
                for token in ("resultado", "result", "sorteo", "boletin", "antio", "loter")
            )
        ]
        print("ANTIOQUENITA_GRAPHQL_CANDIDATES", candidates[:200])
    except (KeyError, TypeError, ValueError) as exc:
        print("ANTIOQUENITA_GRAPHQL_TYPES_PARSE_ERROR", repr(exc), types_response.text[:12000])

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
