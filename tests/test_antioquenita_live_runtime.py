from urllib.parse import urlparse

import httpx
import pytest

from app.sources.fetchers import EmbeddedIframeSourceFetcher, HttpSourceFetcher
from app.sources.four_digit_parsers import (
    AntioquenitaHtmlParser,
    AntioquenitaLoteriaYaHtmlParser,
)


@pytest.mark.integration
def test_antioquenita_official_source_state_is_explicit():
    fetcher = EmbeddedIframeSourceFetcher(
        timeout=30.0,
        allowed_iframe_hosts={"boletin.gana.com.co"},
        fallback_iframe_urls=("https://boletin.gana.com.co/",),
    )
    result = fetcher.fetch("https://rediapuestas.com/resultados/")

    assert 200 <= result.status_code < 300
    assert urlparse(result.url).hostname == "boletin.gana.com.co"
    html = result.content.decode("utf-8", errors="replace")
    assert 'id="root"' in html

    with pytest.raises(ValueError, match="supported result"):
        AntioquenitaHtmlParser().parse(result)


@pytest.mark.integration
def test_antioquenita_lotteriaya_live_fallback_is_parseable_and_cross_checked():
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

    assert day.status_code == 200
    assert afternoon.status_code == 200
    assert independent.status_code == 200
    assert day_records
    assert afternoon_records

    latest_day = day_records[0]
    latest_afternoon = afternoon_records[0]

    for record, expected_type in (
        (latest_day, "ANTIOQUENITA_1"),
        (latest_afternoon, "ANTIOQUENITA_2"),
    ):
        assert record["draw_type"] == expected_type
        assert record["draw_number"] is None
        assert len(record["number"]) == 4
        assert record["number"].isdigit()
        assert record["draw_date"]
        assert 1 <= record["metadata"]["quinta"] <= 9

    independent_html = independent.content.decode("utf-8")
    assert latest_day["number"] in independent_html
    assert latest_afternoon["number"] in independent_html
