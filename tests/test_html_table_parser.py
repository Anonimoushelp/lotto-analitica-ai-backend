from datetime import UTC, datetime

import pytest

from app.sources.fetchers import SourceFetchResult
from app.sources.parsers import HtmlTableParser, SourceParseError


def test_html_table_parser_extracts_chance_rows_and_preserves_leading_zero() -> None:
    html = b"""
    <html><body>
      <table>
        <thead><tr><th>Chance</th><th>Fecha</th><th>Resultado</th></tr></thead>
        <tbody>
          <tr><td>Antioqueñita 1</td><td>20 de Septiembre de 2026</td><td>0153</td></tr>
          <tr><td>Cafeterito Noche</td><td>20 de Septiembre de 2026</td><td>3312</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = SourceFetchResult(
        url="https://example.test/chances",
        status_code=200,
        content=html,
        content_type="text/html",
        fetched_at=datetime.now(UTC),
    )

    records = list(HtmlTableParser().parse(result))

    assert records == [
        {
            "draw_type": "ANTIOQUEÑITA_1",
            "draw_date": "20 de Septiembre de 2026",
            "result": "0153",
        },
        {
            "draw_type": "CAFETERITO_NOCHE",
            "draw_date": "20 de Septiembre de 2026",
            "result": "3312",
        },
    ]


def test_html_table_parser_rejects_missing_result_table() -> None:
    result = SourceFetchResult(
        url="https://example.test/chances",
        status_code=200,
        content=b"<html><body><table><tr><td>nothing</td></tr></table></body></html>",
        content_type="text/html",
        fetched_at=datetime.now(UTC),
    )

    with pytest.raises(SourceParseError, match="supported lottery result table"):
        list(HtmlTableParser().parse(result))
