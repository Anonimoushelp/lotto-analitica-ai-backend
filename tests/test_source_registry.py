from datetime import date

import pytest

from app.sources.contracts import SourceSpec
from app.sources.normalizer import MappingSourceAdapter, SourceNormalizationError
from app.sources.registry import get_source_spec, is_draw_type_supported


def test_registry_contains_all_frontend_lotteries():
    expected = {
        "MILOTO", "BALOTO", "REVANCHA", "SUPER_ASTRO", "ANTIOQUENITA",
        "CHONTICO", "DORADO", "CAFETERITO", "PAISITA", "FANTASTICA",
    }
    from app.sources.registry import SOURCE_REGISTRY

    assert set(SOURCE_REGISTRY) == expected


def test_super_astro_has_independent_draw_types():
    assert is_draw_type_supported("SUPER_ASTRO", "ASTRO_SOL")
    assert is_draw_type_supported("SUPER_ASTRO", "ASTRO_LUNA")
    assert not is_draw_type_supported("SUPER_ASTRO", "DEFAULT")


def test_registry_preserves_unverified_primary_sources():
    spec = get_source_spec("DORADO")
    assert spec.primary_verified is True
    assert "semantic" in spec.notes


def test_mapping_adapter_normalizes_canonical_record():
    spec = SourceSpec(
        lottery_code="TEST",
        draw_types=("TEST_DIA",),
        primary_name="Test Source",
        primary_url="https://example.com/results",
        primary_verified=True,
    )
    adapter = MappingSourceAdapter(spec)

    record = adapter.normalize(
        {
            "draw_type": "TEST_DIA",
            "draw_number": 123,
            "draw_date": "2026-09-21",
            "draw_time": "12:30:00",
            "main_numbers": [4, 12, 23, 31],
            "metadata": {"sign": "CANCER"},
        }
    )

    assert record.lottery_code == "TEST"
    assert record.draw_number == "123"
    assert record.draw_date == date(2026, 9, 21)
    assert record.draw_time.hour == 12
    assert record.main_numbers == [4, 12, 23, 31]
    assert record.metadata["sign"] == "CANCER"
    assert record.source_url == "https://example.com/results"


def test_mapping_adapter_rejects_unknown_draw_type():
    spec = SourceSpec(
        lottery_code="TEST",
        draw_types=("TEST_DIA",),
        primary_name="Test Source",
        primary_url=None,
        primary_verified=False,
    )
    adapter = MappingSourceAdapter(spec)

    with pytest.raises(SourceNormalizationError, match="Unsupported draw type"):
        adapter.normalize(
            {
                "draw_type": "UNKNOWN",
                "draw_number": "1",
                "draw_date": "2026-09-21",
                "main_numbers": [1],
            }
        )


def test_mapping_adapter_supports_provider_field_aliases():
    spec = SourceSpec(
        lottery_code="TEST",
        draw_types=("TEST_DIA",),
        primary_name="Test Source",
        primary_url=None,
        primary_verified=False,
    )
    adapter = MappingSourceAdapter(
        spec,
        field_map={
            "draw_number": "numero_sorteo",
            "draw_date": "fecha",
            "main_numbers": "resultado",
        },
    )

    record = adapter.normalize(
        {
            "draw_type": "TEST_DIA",
            "numero_sorteo": "55",
            "fecha": "2026-09-21",
            "resultado": [1, 2, 3, 4],
        }
    )

    assert record.draw_number == "55"
    assert record.main_numbers == [1, 2, 3, 4]
