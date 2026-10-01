from urllib.parse import urlparse
import re

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

    html = result.content.decode("utf-8", errors="replace")
    print(
        "\nANTIOQUENITA_SOURCE_META "
        f"status={result.status_code} content_type={result.content_type!r} "
        f"bytes={len(result.content)} url={result.url}"
    )
    print("ANTIOQUENITA_SCRIPT_SRCS", re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I))
    print("ANTIOQUENITA_HTML_BEGIN")
    print(html[:20000])
    print("ANTIOQUENITA_HTML_END")

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
