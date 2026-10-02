from urllib.parse import urlparse

import httpx
import pytest

from app.sources.fetchers import EmbeddedIframeSourceFetcher, HttpSourceFetcher
from app.sources.four_digit_parsers import (
    AntioquenitaHtmlParser,
    AntioquenitaLoteriaYaHtmlParser,
)


@pytest.mark.integration
def test_antioquenita_primary_source_reaches_official_iframe():
    fetcher = EmbeddedIframeSourceFetcher(
        timeout=30.0,
        allowed_iframe_hosts={"boletin.gana.com.co"},
        fallback_iframe_urls=("https://boletin.gana.com.co/",),
    )

    result = fetcher.fetch("https://rediapuestas.com/resultados/")

    assert 200 <= result.status_code < 300
    assert urlparse(result.url).hostname == "boletin.gana.com.co"

    with pytest.raises(ValueError, match="supported result"):
        AntioquenitaHtmlParser().parse(result)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("url", "draw_type"),
    (
        (
            "https://www.loteriaya.com.co/chance/antioquenita-dia/historial",
            "ANTIOQUENITA_1",
        ),
        (
            "https://www.loteriaya.com.co/chance/antioquenita-tarde/historial",
            "ANTIOQUENITA_2",
        ),
    ),
)
def test_antioquenita_secondary_live_history(url: str, draw_type: str):
    fetcher = HttpSourceFetcher(
        timeout=30.0,
        allowed_hosts={"www.loteriaya.com.co"},
    )
    result = fetcher.fetch(url)
    records = AntioquenitaLoteriaYaHtmlParser(draw_type=draw_type).parse(result)

    assert result.status_code == 200
    assert records
    latest = records[0]
    assert latest["draw_type"] == draw_type
    assert latest["draw_number"] is None
    assert len(latest["number"]) == 4
    assert latest["number"].isdigit()
    assert latest["draw_date"]
    assert 1 <= latest["metadata"]["quinta"] <= 9


@pytest.mark.integration
def test_antioquenita_secondary_sources_agree_on_latest_result():
    fetcher = HttpSourceFetcher(
        timeout=30.0,
        allowed_hosts={
            "www.loteriaya.com.co",
            "resultadosloterias.com.co",
        },
    )
    day = fetcher.fetch(
        "https://www.loteriaya.com.co/chance/antioquenita-dia/historial"
    )
    afternoon = fetcher.fetch(
        "https://www.loteriaya.com.co/chance/antioquenita-tarde/historial"
    )
    independent = fetcher.fetch("https://resultadosloterias.com.co/")

    day_records = AntioquenitaLoteriaYaHtmlParser(
        draw_type="ANTIOQUENITA_1"
    ).parse(day)
    afternoon_records = AntioquenitaLoteriaYaHtmlParser(
        draw_type="ANTIOQUENITA_2"
    ).parse(afternoon)

    independent_html = independent.content.decode("utf-8")
    assert independent.status_code == 200
    assert (
        day_records[0]["draw_date"] in independent_html
        or day_records[0]["number"] in independent_html
    )
    assert (
        afternoon_records[0]["draw_date"] in independent_html
        or afternoon_records[0]["number"] in independent_html
    )
