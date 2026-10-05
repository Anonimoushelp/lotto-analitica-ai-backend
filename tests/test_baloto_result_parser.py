from datetime import UTC, datetime

from app.sources.fetchers import SourceFetchResult
from app.sources.parsers import BalotoResultPageParser


DETAIL_TEMPLATE = """
<html><body>
SORTEO 2.712
Lunes
{date}
ACUMULADO DEL SORTEO: $59.600 MILLONES
{numbers}
TOTAL GANADORES
15.783
</body></html>
"""


def _result(numbers: str, date: str) -> SourceFetchResult:
    return SourceFetchResult(
        url="https://www.baloto.com/resultados-baloto/2712",
        status_code=200,
        content=DETAIL_TEMPLATE.format(date=date, numbers=numbers).encode(),
        content_type="text/html",
        fetched_at=datetime.now(UTC),
    )


def test_baloto_parser_reads_current_official_detail_layout() -> None:
    records = list(
        BalotoResultPageParser(draw_type="BALOTO").parse(
            _result("04 15 17 22 23 10", "21 de Septiembre de 2026")
        )
    )

    assert records == [
        {
            "game_type": "BALOTO",
            "draw_number": "2712",
            "draw_date": "2026-09-21",
            "main_numbers": [4, 15, 17, 22, 23],
            "metadata": {"source_format": "official_draw_page"},
            "superbalota": [10],
        }
    ]


def test_revancha_parser_reads_current_official_detail_layout() -> None:
    records = list(
        BalotoResultPageParser(draw_type="REVANCHA").parse(
            _result("05 32 33 36 40 04", "21 de Septiembre de 2026")
        )
    )

    assert records == [
        {
            "game_type": "REVANCHA",
            "draw_number": "2712",
            "draw_date": "2026-09-21",
            "main_numbers": [5, 32, 33, 36, 40],
            "metadata": {"source_format": "official_draw_page"},
            "revancha_bonus": [4],
        }
    ]
