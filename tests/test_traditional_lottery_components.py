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
