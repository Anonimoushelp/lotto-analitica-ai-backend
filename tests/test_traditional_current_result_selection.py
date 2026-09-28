from datetime import UTC, datetime

import pytest

from app.sources.fetchers import SourceFetchResult
from app.sources.provider_registry import build_traditional_lottery_components


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
