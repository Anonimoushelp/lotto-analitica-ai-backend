from datetime import date

import pytest

from app.integrations.colombia_lotteries import BalotoAdapter, MiLotoAdapter
from app.integrations.colombia_registry import RevanchaAdapter


def test_baloto_rejects_miloto_shape():
    adapter = BalotoAdapter()
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 100,
                "fecha": "2026-09-13",
                "resultado": [1, 2, 3, 4, 5],
            }
        )


def test_miloto_rejects_baloto_bonus_shape():
    adapter = MiLotoAdapter()
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 100,
                "fecha": "2026-09-13",
                "resultado": [1, 2, 3, 4, 5, 6],
            }
        )


def test_revancha_has_independent_source_provenance():
    result = RevanchaAdapter().parse_draw(
        {
            "sorteo": "Sorteo #100",
            "fecha": date(2026, 9, 13),
            "resultado": [1, 8, 17, 29, 41, 9],
        }
    )
    assert result.source == "revancha-colombia"
    assert result.main_numbers == [1, 8, 17, 29, 41]
    assert result.bonus_numbers == [9]


def test_provider_rejects_ambiguous_result_format():
    adapter = BalotoAdapter()
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 101,
                "fecha": "2026-09-13",
                "resultado": "1, 7, 12, 28, 43, 16",
            }
        )


def test_provider_rejects_invalid_calendar_date():
    adapter = BalotoAdapter()
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 102,
                "fecha": "2026-02-30",
                "resultado": [1, 7, 12, 28, 43, 16],
            }
        )


def test_provider_rejects_extra_fields_before_normalization():
    adapter = BalotoAdapter()
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 103,
                "fecha": "2026-09-13",
                "resultado": [1, 7, 12, 28, 43, 16],
                "url": "https://attacker.invalid/provider",
            }
        )


def test_provider_metadata_is_passed_through_canonical_validation():
    adapter = BalotoAdapter()
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 104,
                "fecha": "2026-09-13",
                "resultado": [1, 7, 12, 28, 43, 16],
                "metadata": {"raw": b"not-json"},
            }
        )
