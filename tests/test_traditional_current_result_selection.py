import json
from datetime import UTC, datetime

import pytest

from app.sources.fetchers import SourceFetchResult
from app.sources.provider_registry import build_traditional_lottery_components


def _json_result(payload: list[dict]) -> SourceFetchResult:
    return SourceFetchResult(
        url=(
            "https://www.datos.gov.co/resource/i3kx-3zps.json"
            "?loter_a=Loteria%20Santander"
            "&tipo_de_premio=Mayor"
            "&%24order=n_mero_del_sorteo%20DESC"
            "&%24limit=1"
        ),
        content=json.dumps(payload).encode(),
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        status_code=200,
        content_type="application/json",
    )


def _result(html: str) -> SourceFetchResult:
    return SourceFetchResult(
        url="https://example.test/resultados",
        content=html.encode(),
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        status_code=200,
        content_type="text/html; charset=utf-8",
    )


@pytest.mark.parametrize(
    ("lottery_code", "html", "expected_draw", "expected_date", "expected_number", "expected_series"),
    [
        (
            "LOTERIA_CAUCA",
            """<html><body>
                Sorteo: 2629
                Fecha: 2026-09-19
                $8.000 Millones Premio Mayor
                3 4 0 9
                Serie 260
            </body></html>""",
            "2629",
            "2026-09-19",
            3409,
            "260",
        ),
        (
            "LOTERIA_HUILA",
            """<html><body>
                Sorteo 4774
                22 de septiembre de 2026
                PREMIO MAYOR 1547
                Número 082 Serie
                Plan de Premios 2025
            </body></html>""",
            "4774",
            "2026-09-22",
            1547,
            "082",
        ),
        (
            "LOTERIA_TOLIMA",
            """<html><body>
                Resultados Sorteo 4188
                Lunes, 21 de septiembre de 2026
                PREMIO MAYOR 3.500 MILLONES
                NÚMERO 4008 SERIE 055
                Resultado histórico 2025
            </body></html>""",
            "4188",
            "2026-09-21",
            4008,
            "055",
        ),
        (
            "LOTERIA_MANIZALES",
            """<html><body>
                4974
                Resultados 23 de septiembre de 2026 - Premio Mayor $ 3.000 Millones
                1 1 9 9 3 3 3 3
                2 2 1 1 9 9
                Próximo Sorteo 4975 - 30 de septiembre de 2026
            </body></html>""",
            "4974",
            "2026-09-23",
            1933,
            "219",
        ),
    ],
)
def test_traditional_parser_prefers_labeled_major_result_and_current_date(
    lottery_code,
    html,
    expected_draw,
    expected_date,
    expected_number,
    expected_series,
):
    parser, adapter = build_traditional_lottery_components(lottery_code)

    records = list(parser.parse(_result(html), lottery_code))
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == expected_draw
    assert normalized.draw_date.isoformat() == expected_date
    assert normalized.main_numbers == [expected_number]
    assert normalized.metadata["raw_result"] == f"{expected_number:04d}"
    assert normalized.metadata["series"] == expected_series


def test_santander_official_open_data_rejects_non_array_payload():
    parser, _ = build_traditional_lottery_components("LOTERIA_SANTANDER")

    invalid = SourceFetchResult(
        url="https://www.datos.gov.co/resource/i3kx-3zps.json",
        content=b'{"error":"bad payload"}',
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        status_code=200,
        content_type="application/json",
    )

    with pytest.raises(ValueError, match="JSON array"):
        list(parser.parse(invalid, "LOTERIA_SANTANDER"))



def test_santander_official_open_data_extracts_latest_major_result():
    parser, adapter = build_traditional_lottery_components("LOTERIA_SANTANDER")

    records = list(
        parser.parse(
            _json_result(
                [
                    {
                        "a_o_del_sorteo": "2026",
                        "mes_del_sorteo": "9",
                        "fecha_del_sorteo": "18/09/2026",
                        "loter_a": "Loteria Santander",
                        "n_mero_del_sorteo": "5088",
                        "numero_billete_ganador": "0937",
                        "numero_serie_ganadora": "278",
                        "tipo_de_premio": "Mayor",
                    },
                    {
                        "a_o_del_sorteo": "2026",
                        "mes_del_sorteo": "9",
                        "fecha_del_sorteo": "25/09/2026",
                        "loter_a": "Loteria Santander",
                        "n_mero_del_sorteo": "5089",
                        "numero_billete_ganador": "0151",
                        "numero_serie_ganadora": "055",
                        "tipo_de_premio": "Mayor",
                    },
                    {
                        "a_o_del_sorteo": "2026",
                        "mes_del_sorteo": "9",
                        "fecha_del_sorteo": "25/09/2026",
                        "loter_a": "Loteria Santander",
                        "n_mero_del_sorteo": "5089",
                        "numero_billete_ganador": "2693",
                        "numero_serie_ganadora": "165",
                        "tipo_de_premio": "Seco",
                    },
                    {
                        "a_o_del_sorteo": "2026",
                        "mes_del_sorteo": "9",
                        "fecha_del_sorteo": "25/09/2026",
                        "loter_a": "Otra",
                        "n_mero_del_sorteo": "9999",
                        "numero_billete_ganador": "9999",
                        "numero_serie_ganadora": "999",
                        "tipo_de_premio": "Mayor",
                    },
                ]
            ),
            "LOTERIA_SANTANDER",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "5089"
    assert normalized.draw_date.isoformat() == "2026-09-25"
    assert normalized.main_numbers == [151]
    assert normalized.metadata["raw_result"] == "0151"
    assert normalized.metadata["series"] == "055"
    assert normalized.metadata["source_format"] == "official_open_data_socrata"
    assert normalized.metadata["source_verified"] is True



def test_boyaca_parser_does_not_take_year_as_draw_number_or_result():
    parser, adapter = build_traditional_lottery_components("LOTERIA_BOYACA")

    records = list(
        parser.parse(
            _result(
                """<html><head><title>Sorteo 2026</title></head><body>
                Resultado sorteo #4643
                Sábado 26 de septiembre de 2026
                Número Ganador 9 8 8 2
                Serie 2 7 0
                </body></html>"""
            ),
            "LOTERIA_BOYACA",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "4643"
    assert normalized.draw_date.isoformat() == "2026-09-26"
    assert normalized.main_numbers == [9882]
    assert normalized.metadata["raw_result"] == "9882"
    assert normalized.metadata["series"] == "270"


def test_traditional_parser_selects_latest_past_draw_when_page_contains_future_and_old_dates():
    parser, adapter = build_traditional_lottery_components("LOTERIA_MANIZALES")

    records = list(
        parser.parse(
            _result(
                """<html><body>
                Sorteo 4975 Septiembre 30 de 2026
                PREMIO MAYOR 9999
                Serie 999
                Sorteo 4974 Septiembre 23 de 2026
                PREMIO MAYOR 1234
                Serie 321
                Plan de Premios 2025
                </body></html>"""
            ),
            "LOTERIA_MANIZALES",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "4974"
    assert normalized.draw_date.isoformat() == "2026-09-23"
    assert normalized.main_numbers == [1234]
    assert normalized.metadata["series"] == "321"


def test_traditional_parser_rejects_unlabeled_year_only_result():
    parser, _ = build_traditional_lottery_components("LOTERIA_CAUCA")

    with pytest.raises(ValueError, match="recognizable four-digit result"):
        list(
            parser.parse(
                _result(
                    """<html><body>
                    Sorteo del año 2026
                    Fecha 2026-09-19
                    Información general sin número ganador
                    </body></html>"""
                ),
                "LOTERIA_CAUCA",
            )
        )


def test_cauca_official_homepage_layout_extracts_current_result():
    parser, adapter = build_traditional_lottery_components("LOTERIA_CAUCA")

    records = list(
        parser.parse(
            _result(
                """<html><body>
                Sorteo: 2630
                Fecha: 2026-09-26
                <h2>$8.000</h2>
                <div>Millones</div>
                Premio Mayor
                7 5 6 7
                Serie 058
                </body></html>"""
            ),
            "LOTERIA_CAUCA",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "2630"
    assert normalized.draw_date.isoformat() == "2026-09-26"
    assert normalized.main_numbers == [7567]
    assert normalized.metadata["raw_result"] == "7567"
    assert normalized.metadata["series"] == "058"
    assert (
        normalized.metadata["source_format"]
        == "official_homepage_major_result_block"
    )


def test_cauca_homepage_does_not_mix_ordinary_and_extraordinary_draw_blocks():
    parser, adapter = build_traditional_lottery_components("LOTERIA_CAUCA")

    records = list(
        parser.parse(
            _result(
                """<html><body>
                <section>
                  Sorteo: 2630
                  Fecha: 2026-09-26
                  $8.000 Millones
                  Premio Mayor
                  7 5 6 7
                  Serie 058
                </section>
                <section>
                  Sorteo: 0009
                  Fecha: 2026-06-02
                  $12.000 Millones
                  Extraordinario
                  1 9 3 3
                  Serie 2010
                </section>
                </body></html>"""
            ),
            "LOTERIA_CAUCA",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "2630"
    assert normalized.draw_date.isoformat() == "2026-09-26"
    assert normalized.main_numbers == [7567]
    assert normalized.metadata["series"] == "058"


def test_risaralda_requires_major_result_context_instead_of_unrelated_four_digit_values():
    parser, _ = build_traditional_lottery_components("LOTERIA_RISARALDA")

    with pytest.raises(ValueError, match="recognizable major result"):
        list(
            parser.parse(
                _result(
                    """<html><body>
                    Sorteo No. 2968
                    viernes 25 de septiembre de 2026
                    Chontico Día
                    Número 8437 - 5
                    Información comercial 2026
                    </body></html>"""
                ),
                "LOTERIA_RISARALDA",
            )
        )


def test_risaralda_current_major_result_layout_extracts_verified_result():
    parser, adapter = build_traditional_lottery_components("LOTERIA_RISARALDA")

    records = list(
        parser.parse(
            _result(
                """<html><body>
                Sorteo No. 2968
                viernes 25 de septiembre de 2026
                Premio mayor
                6 7 3 1
                Serie 1 9 7
                </body></html>"""
            ),
            "LOTERIA_RISARALDA",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "2968"
    assert normalized.draw_date.isoformat() == "2026-09-25"
    assert normalized.main_numbers == [6731]
    assert normalized.metadata["raw_result"] == "6731"
    assert normalized.metadata["series"] == "197"


def test_risaralda_official_consultation_table_layout_extracts_major_result_and_series():
    parser, adapter = build_traditional_lottery_components("LOTERIA_RISARALDA")

    records = list(
        parser.parse(
            _result(
                """<html><body>
                <span>2968+</span>
                <span>Sorteos jugados</span>
                </body></html>
                <!-- RISARALDA_OFFICIAL_CONSULTATION -->
                <table>
                  <thead>
                    <tr><th>Nombre</th><th>Total Premio</th><th>Numero</th><th>Serie</th><th>Ciudad</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>PREMIO MAYOR</td><td>$ 2.333.333.333</td><td>6731</td><td>197</td><td>PEREIRA</td></tr>
                    <tr><td>SECO EL GORDO DE LA RISARALDA</td><td>$ 300.000.000</td><td>4842</td><td>192</td><td>PEREIRA</td></tr>
                  </tbody>
                </table>"""
            ),
            "LOTERIA_RISARALDA",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "2968"
    assert normalized.draw_date.isoformat() == "2026-09-25"
    assert normalized.main_numbers == [6731]
    assert normalized.metadata["raw_result"] == "6731"
    assert normalized.metadata["series"] == "197"
    assert normalized.metadata["source_verified"] is True
    assert normalized.metadata["source_format"] == "official_institutional_composite"


def test_risaralda_official_institutional_composite_layout_extracts_current_result():
    parser, adapter = build_traditional_lottery_components("LOTERIA_RISARALDA")

    records = list(
        parser.parse(
            _result(
                """<html><body>
                <span>2968+</span>
                <span>Sorteos jugados</span>
                <article>Noticias 18 de septiembre de 2026</article>
                </body></html>
                <!-- RISARALDA_OFFICIAL_CONSULTATION -->
                <html><body>
                <h1>Consulta de Lotería</h1>
                <div>PREMIO MAYOR</div>
                <div>Número 6731</div>
                <div>Serie 197</div>
                <div>SECO EL GORDO DE LA RISARALDA 4842 192</div>
                </body></html>"""
            ),
            "LOTERIA_RISARALDA",
        )
    )
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "2968"
    assert normalized.draw_date.isoformat() == "2026-09-25"
    assert normalized.main_numbers == [6731]
    assert normalized.metadata["raw_result"] == "6731"
    assert normalized.metadata["series"] == "197"
    assert normalized.metadata["source_verified"] is True
    assert normalized.metadata["source_format"] == "official_institutional_composite"
