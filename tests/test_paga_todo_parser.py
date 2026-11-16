from datetime import UTC, datetime

import pytest

from app.sources.fetchers import SourceFetchResult
from app.sources.parsers import PagaTodoResultPageParser, SourceParseError


def _result(html: bytes, url: str) -> SourceFetchResult:
    return SourceFetchResult(
        url=url,
        status_code=200,
        content=html,
        content_type="text/html",
        fetched_at=datetime.now(UTC),
    )


def test_paga_todo_parser_keeps_legacy_la_quinta_markup():
    html = b"""
    <section>
      <h2>Sorteo El Dorado D&iacute;a</h2>
      <div>19/09/2026</div>
      <div>N&uacute;mero Ganador</div>
      <div>4 6 6 0 - 9 La Quinta</div>
    </section>
    """
    records = list(
        PagaTodoResultPageParser(draw_types=("DORADO_DIA",)).parse(
            _result(html, "https://www.pagatodo.com.co/resultados/la-quinta/")
        )
    )

    assert records == [
        {
            "draw_type": "DORADO_DIA",
            "draw_date": "2026-09-19",
            "result": "4660",
            "metadata": {
                "source_format": "official_pagatodo_results_page",
                "additional_value": "9",
            },
        }
    ]


def test_paga_todo_parser_reads_all_three_current_chance_draws():
    html = b"""
    <section>
      <h2>Sorteo El Dorado D&iacute;a</h2>
      <div>14/11/2026</div>
      <div>N&uacute;mero Ganador</div>
      <div>5 4 1 5 - 0 La Quinta</div>
      <div>Fecha 14/11/2026</div>
      <h2>Sorteo El Dorado Tarde</h2>
      <div>14/11/2026</div>
      <div>N&uacute;mero Ganador</div>
      <div>5 3 6 6 - 5 La Quinta</div>
      <div>Fecha 14/11/2026</div>
      <h2>Sorteo El Dorado Noche</h2>
      <div>15/11/2026</div>
      <div>N&uacute;mero Ganador</div>
      <div>7 5 5 0 - 1 La Quinta</div>
      <div>Fecha 15/11/2026</div>
    </section>
    """
    records = list(
        PagaTodoResultPageParser(
            draw_types=("DORADO_DIA", "DORADO_TARDE", "DORADO_NOCHE")
        ).parse(
            _result(html, "https://www.pagatodo.com.co/resultados/la-quinta/")
        )
    )

    assert [(item["draw_type"], item["draw_date"], item["result"]) for item in records] == [
        ("DORADO_DIA", "2026-11-14", "5415"),
        ("DORADO_TARDE", "2026-11-14", "5366"),
        ("DORADO_NOCHE", "2026-11-15", "7550"),
    ]
    assert [item["metadata"]["additional_value"] for item in records] == ["0", "5", "1"]


def test_paga_todo_parser_supports_results_page_without_la_quinta_extra():
    html = b"""
    <section>
      <h2>Sorteo El Dorado D&iacute;a</h2>
      <div>Dorado</div>
      <div>N&uacute;mero Ganador</div>
      <div>0 0 2 5</div>
      <div>Fecha</div>
      <div>14/11/2026</div>
      <div>Hora 10:55 a.m.</div>
    </section>
    """
    records = list(
        PagaTodoResultPageParser(draw_types=("DORADO_DIA",)).parse(
            _result(html, "https://www.pagatodo.com.co/resultados/sorteos/")
        )
    )

    assert records[0]["result"] == "0025"
    assert records[0]["draw_date"] == "2026-11-14"
    assert "additional_value" not in records[0]["metadata"]


@pytest.mark.parametrize(
    "html",
    [
        b"<section><h2>Sorteo El Dorado D&iacute;a</h2><div>14/11/2026</div></section>",
        b"<section><h2>Sorteo El Dorado D&iacute;a</h2><div>N&uacute;mero Ganador 12345</div><div>Fecha 14/11/2026</div></section>",
    ],
)
def test_paga_todo_parser_rejects_missing_or_invalid_result(html: bytes):
    with pytest.raises(SourceParseError):
        list(
            PagaTodoResultPageParser(draw_types=("DORADO_DIA",)).parse(
                _result(html, "https://www.pagatodo.com.co/resultados/sorteos/")
            )
        )


def test_paga_todo_parser_rejects_unsupported_draw_type():
    with pytest.raises(ValueError):
        PagaTodoResultPageParser(draw_types=("LA_QUINTA",))
