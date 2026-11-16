import html as html_lib
import re
from datetime import date
from urllib.parse import urlparse

import pytest

from app.sources.fetchers import EmbeddedIframeSourceFetcher, HttpSourceFetcher
from app.sources.four_digit_parsers import (
    AntioquenitaHtmlParser,
    AntioquenitaLoteriaYaHtmlParser,
)


_MONTH_NAMES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _latest_shared_record(records, independent_html):
    """Return the newest record whose date and number also appear in the secondary page."""
    without_scripts = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        independent_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    visible_text = " ".join(
        html_lib.unescape(re.sub(r"<[^>]+>", " ", without_scripts)).split()
    )

    for record in sorted(records, key=lambda item: item["draw_date"], reverse=True):
        draw_date = date.fromisoformat(record["draw_date"])
        month = _MONTH_NAMES[draw_date.month - 1]
        number = r"\s*".join(re.escape(digit) for digit in record["number"])
        row_pattern = re.compile(
            rf"\b{draw_date.day}\s+de\s+{month}"
            rf"(?:\s+de\s+{draw_date.year})?\s+{number}(?!\d)",
            re.IGNORECASE,
        )
        if row_pattern.search(visible_text):
            return record
    return None


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
            "resultadoschancehoy.com",
        },
    )
    day = fetcher.fetch(
        "https://www.loteriaya.com.co/chance/antioquenita-dia/historial"
    )
    afternoon = fetcher.fetch(
        "https://www.loteriaya.com.co/chance/antioquenita-tarde/historial"
    )
    independent_day = fetcher.fetch("https://resultadoschancehoy.com/resultados-antioquenita-dia")
    independent_afternoon = fetcher.fetch("https://resultadoschancehoy.com/resultados-antioquenita-tarde")

    day_records = AntioquenitaLoteriaYaHtmlParser(
        draw_type="ANTIOQUENITA_1"
    ).parse(day)
    afternoon_records = AntioquenitaLoteriaYaHtmlParser(
        draw_type="ANTIOQUENITA_2"
    ).parse(afternoon)

    assert day.status_code == 200
    assert afternoon.status_code == 200
    assert independent_day.status_code == 200
    assert independent_afternoon.status_code == 200
    assert day_records
    assert afternoon_records

    independent_day_html = independent_day.content.decode("utf-8")
    independent_afternoon_html = independent_afternoon.content.decode("utf-8")
    common_day = _latest_shared_record(day_records, independent_day_html)
    common_afternoon = _latest_shared_record(afternoon_records, independent_afternoon_html)
    assert common_day is not None, "No shared Antioqueñita Día result was found"
    assert common_afternoon is not None, "No shared Antioqueñita Tarde result was found"

    for record, expected_type in (
        (common_day, "ANTIOQUENITA_1"),
        (common_afternoon, "ANTIOQUENITA_2"),
    ):
        assert record["draw_type"] == expected_type
        assert record["draw_number"] is None
        assert len(record["number"]) == 4
        assert record["number"].isdigit()
        assert record["draw_date"]
        assert 1 <= record["metadata"]["quinta"] <= 9

