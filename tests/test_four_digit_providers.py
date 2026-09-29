from datetime import UTC, datetime

import pytest

from app.sources.fetchers import SourceFetchResult
from app.sources.four_digit_adapters import (
    AntioquenitaAdapter,
    CafeteritoAdapter,
    ChonticoAdapter,
    DoradoAdapter,
    FantasticaAdapter,
    PaisitaAdapter,
)
from app.sources.four_digit_parsers import (
    AntioquenitaHtmlParser,
    AntioquenitaJsonParser,
    CafeteritoJsonParser,
    ChonticoJsonParser,
    DoradoJsonParser,
    FantasticaJsonParser,
    PaisitaJsonParser,
)


@pytest.mark.parametrize(
    ("parser", "adapter", "payload", "draw_type", "raw_result"),
    [
        (
            AntioquenitaJsonParser(),
            AntioquenitaAdapter(),
            {
                "tipo": "ANTIOQUENITA_2",
                "sorteo": 101,
                "fecha": "2026-09-20",
                "resultado": "0153",
            },
            "ANTIOQUENITA_2",
            "0153",
        ),
        (
            ChonticoJsonParser(),
            ChonticoAdapter(),
            {
                "tipo": "CHONTICO_DIA",
                "sorteo": 6725,
                "fecha": "2026-09-20",
                "resultado": "6725",
            },
            "CHONTICO_DIA",
            "6725",
        ),
        (
            DoradoJsonParser(),
            DoradoAdapter(),
            {
                "tipo": "DORADO_NOCHE",
                "sorteo": 20260920,
                "fecha": "2026-09-20",
                "resultado": "0982",
                "additional_value": 7,
            },
            "DORADO_NOCHE",
            "0982",
        ),
        (
            CafeteritoJsonParser(),
            CafeteritoAdapter(),
            {
                "tipo": "CAFETERITO_TARDE",
                "sorteo": 674,
                "fecha": "2026-09-19",
                "resultado": "0674",
            },
            "CAFETERITO_TARDE",
            "0674",
        ),
        (
            PaisitaJsonParser(),
            PaisitaAdapter(),
            {
                "tipo": "PAISITA_NOCHE",
                "sorteo": 3946,
                "fecha": "2026-09-20",
                "resultado": "3946",
                "animal": "Caballo",
            },
            "PAISITA_NOCHE",
            "3946",
        ),
        (
            FantasticaJsonParser(),
            FantasticaAdapter(),
            {
                "tipo": "FANTASTICA_DIA",
                "sorteo": 1,
                "fecha": "2026-09-21",
                "resultado": "0512",
                "additional_value": 8,
            },
            "FANTASTICA_DIA",
            "0512",
        ),
    ],
)
def test_four_digit_provider_parser_and_adapter(
    parser, adapter, payload, draw_type, raw_result
):
    parsed = parser.parse_record(payload)
    record = adapter.normalize(parsed)

    assert record.draw_type == draw_type
    assert record.main_numbers == [int(raw_result)]
    assert record.metadata["raw_result"] == raw_result
    assert record.metadata["digit_count"] == 4


def test_paisita_preserves_animal_metadata():
    parsed = PaisitaJsonParser().parse_record(
        {
            "tipo": "PAISITA_NOCHE",
            "sorteo": 3946,
            "fecha": "2026-09-20",
            "resultado": "3946",
            "animal": "Caballo",
        }
    )
    assert parsed["metadata"]["animal"] == "Caballo"


def test_dorado_does_not_promote_additional_value_to_bonus():
    parsed = DoradoJsonParser().parse_record(
        {
            "tipo": "DORADO_NOCHE",
            "sorteo": 1,
            "fecha": "2026-09-20",
            "resultado": "0982",
            "additional_value": 7,
        }
    )
    assert parsed["metadata"]["additional_value"] == 7
    assert "bonus_numbers" not in parsed


@pytest.mark.parametrize(
    ("parser", "payload"),
    [
        (
            AntioquenitaJsonParser(),
            {
                "tipo": "ANTIOQUENITA_1",
                "sorteo": 1,
                "fecha": "2026-09-20",
                "resultado": "123",
            },
        ),
        (
            ChonticoJsonParser(),
            {
                "tipo": "CHONTICO_DIA",
                "sorteo": 1,
                "fecha": "2026-09-20",
                "resultado": "12345",
            },
        ),
        (
            PaisitaJsonParser(),
            {
                "tipo": "PAISITA_DIA",
                "sorteo": 1,
                "fecha": "2026-09-20",
                "resultado": "12A4",
            },
        ),
    ],
)
def test_four_digit_parser_rejects_invalid_result(parser, payload):
    with pytest.raises(Exception, match="Four-digit result"):
        parser.parse_record(payload)


def test_antioquenita_html_parser_extracts_day_result_and_quinta() -> None:
    html = """
    <section>
      <h2>Antioqueñita 1</h2>
      <div>Sorteo 6771</div>
      <div>Lunes 28 de Septiembre de 2026</div>
      <div>Resultado: 0166</div>
      <div>La Quinta: 5</div>
    </section>
    """
    result = SourceFetchResult(
        url="https://boletin.gana.com.co/",
        status_code=200,
        content=html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
        fetched_at=datetime(2026, 9, 28, 15, 5, tzinfo=UTC),
    )

    parsed = list(AntioquenitaHtmlParser().parse(result))

    assert parsed == [
        {
            "draw_type": "ANTIOQUENITA_1",
            "draw_number": "6771",
            "draw_date": "2026-09-28",
            "number": "0166",
            "metadata": {
                "raw_result": "0166",
                "digit_count": 4,
                "source_format": "official_rediapuestas_iframe_html",
                "quinta": 5,
            },
        }
    ]


def test_antioquenita_html_parser_extracts_both_daily_draw_types() -> None:
    html = """
    <section>
      <h2>Antioqueñita 1</h2>
      <div>Sorteo 6771</div><div>28 de Septiembre de 2026</div>
      <div>Resultado 0166</div><div>Quinta 5</div>
    </section>
    <section>
      <h2>Antioqueñita 2</h2>
      <div>Sorteo 6772</div><div>28 de Septiembre de 2026</div>
      <div>Resultado 9538</div><div>Quinta 5</div>
    </section>
    """
    result = SourceFetchResult(
        url="https://boletin.gana.com.co/",
        status_code=200,
        content=html.encode("utf-8"),
        content_type="text/html",
        fetched_at=datetime(2026, 9, 28, 21, 0, tzinfo=UTC),
    )

    parsed = list(AntioquenitaHtmlParser().parse(result))

    assert [(row["draw_type"], row["draw_number"], row["number"]) for row in parsed] == [
        ("ANTIOQUENITA_1", "6771", "0166"),
        ("ANTIOQUENITA_2", "6772", "9538"),
    ]
