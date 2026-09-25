from datetime import UTC, datetime

import pytest

from app.scheduler.catalog_integration import (
    IntegrationStatus,
    build_catalog_scheduler_bindings,
)
from app.sources.fetchers import SourceFetchResult
from app.sources.provider_registry import build_traditional_lottery_components


def _result(html: str) -> SourceFetchResult:
    return SourceFetchResult(
        url="https://example.test/resultados",
        content=html.encode(),
        fetched_at=datetime(2026, 9, 21, tzinfo=UTC),
        status_code=200,
        content_type="text/html; charset=utf-8",
    )


def test_traditional_parser_and_adapter_preserve_major_result_and_series():
    parser, adapter = build_traditional_lottery_components("LOTERIA_TOLIMA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Sorteo 4187 - lunes 14 de septiembre de 2026 "
                "Número 6845 Serie 051"
                "</body></html>"
            ),
            "LOTERIA_TOLIMA",
        )
    )
    normalized = adapter.normalize(records[0])
    assert normalized.draw_number == "4187"
    assert normalized.draw_date.isoformat() == "2026-09-14"
    assert normalized.main_numbers == [6845]
    assert normalized.metadata["series"] == "051"
    assert normalized.metadata["raw_result"] == "6845"


def test_all_catalog_ordinary_codes_have_component_mapping():
    bindings = build_catalog_scheduler_bindings()
    for binding in bindings:
        if binding.integration_status is not IntegrationStatus.EXTRAORDINARY_ONLY:
            parser, adapter = build_traditional_lottery_components(binding.lottery_code)
            assert parser is not None
            assert adapter.spec.lottery_code == binding.lottery_code


def test_traditional_adapter_rejects_non_four_digit_major_result():
    _, adapter = build_traditional_lottery_components("LOTERIA_TOLIMA")
    with pytest.raises(ValueError, match="exactly four digits"):
        adapter.normalize(
            {
                "draw_type": "LOTERIA_TOLIMA_ORDINARY",
                "draw_date": "2026-09-14",
                "draw_number": "4187",
                "main_numbers": [123],
                "metadata": {"raw_result": "123"},
            }
        )



def test_traditional_parser_accepts_abbreviated_month_and_numeric_date():
    parser, _ = build_traditional_lottery_components("LOTERIA_TOLIMA")
    abbreviated = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4188 - 21 de sept. de 2026 "
                "Número 4008 Serie 055</body></html>"
            ),
            "LOTERIA_TOLIMA",
        )
    )
    numeric = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4188 - 21/09/2026 "
                "Número 4008 Serie 055</body></html>"
            ),
            "LOTERIA_TOLIMA",
        )
    )
    assert abbreviated[0]["draw_date"] == "2026-09-21"
    assert numeric[0]["draw_date"] == "2026-09-21"
    assert abbreviated[0]["main_numbers"] == [4008]
    assert numeric[0]["main_numbers"] == [4008]


def test_traditional_parser_accepts_iso_date_and_colon_draw_label():
    parser, _ = build_traditional_lottery_components("LOTERIA_CAUCA")
    records = list(
        parser.parse(
            _result(
                "<html><body>Sorteo: 2629 Fecha: 2026-09-19 "
                "3 4 0 9 Serie 260</body></html>"
            ),
            "LOTERIA_CAUCA",
        )
    )
    assert records[0]["draw_number"] == "2629"
    assert records[0]["draw_date"] == "2026-09-19"
    assert records[0]["main_numbers"] == [3409]
    assert records[0]["metadata"]["series"] == "260"


def test_traditional_parser_accepts_month_first_real_format():
    parser, _ = build_traditional_lottery_components("LOTERIA_VALLE")
    records = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4867 Septiembre 23 2026 "
                "Número 4356 Serie 149</body></html>"
            ),
            "LOTERIA_VALLE",
        )
    )
    assert records[0]["draw_number"] == "4867"
    assert records[0]["draw_date"] == "2026-09-23"
    assert records[0]["main_numbers"] == [4356]
    assert records[0]["metadata"]["series"] == "149"


def test_traditional_parser_accepts_quindio_result_series_pair():
    parser, _ = build_traditional_lottery_components("LOTERIA_QUINDIO")
    records = list(
        parser.parse(
            _result(
                "<html><body>Resultado Sorteo 3016 del 2026-09-17 "
                "Premio Mayor 3853-160</body></html>"
            ),
            "LOTERIA_QUINDIO",
        )
    )
    assert records[0]["draw_number"] == "3016"
    assert records[0]["draw_date"] == "2026-09-17"
    assert records[0]["main_numbers"] == [3853]
    assert records[0]["metadata"]["series"] == "160"
