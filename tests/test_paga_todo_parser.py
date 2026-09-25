from datetime import datetime, timezone

from app.sources.fetchers import SourceFetchResult
from app.sources.parsers import PagaTodoResultPageParser


def test_paga_todo_parser_decodes_html_entities():
    html = b"""
    <section>
      <h2>Sorteo El Dorado D&amp;iacute;a</h2>
      <div>19/09/2026</div>
      <div>N&amp;uacute;mero Ganador</div>
      <div>4 6 6 0 - 9 La Quinta</div>
    </section>
    """
    result = SourceFetchResult(
        url="https://www.pagatodo.com.co/resultados-loto-core/la-quinta/",
        status_code=200,
        content=html,
        content_type="text/html",
        fetched_at=datetime.now(timezone.utc),
    )

    records = list(
        PagaTodoResultPageParser(draw_types=("DORADO_DIA",)).parse(result)
    )

    assert records == [
        {
            "draw_type": "DORADO_DIA",
            "draw_date": "2026-09-19",
            "result": "4660",
            "metadata": {
                "additional_value": "9",
                "source_format": "official_la_quinta_page",
            },
        }
    ]
