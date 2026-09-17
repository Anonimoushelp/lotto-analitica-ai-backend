from datetime import date

import pytest

from app.integrations.colombia_lotteries import BalotoAdapter, MiLotoAdapter
from app.integrations.colombia_registry import (
    RevanchaAdapter,
    build_colombia_source_adapters,
    get_colombia_source_adapter,
)


def test_supported_sources_are_explicit_and_distinct():
    adapters = build_colombia_source_adapters()

    assert set(adapters) == {
        "baloto-colombia",
        "revancha-colombia",
        "miloto-colombia",
    }
    assert isinstance(adapters["baloto-colombia"], BalotoAdapter)
    assert isinstance(adapters["revancha-colombia"], RevanchaAdapter)
    assert isinstance(adapters["miloto-colombia"], MiLotoAdapter)


def test_baloto_payload_is_normalized():
    result = get_colombia_source_adapter(" baloto-colombia ").parse_draw(
        {
            "sorteo": "Sorteo #12345",
            "fecha": "13 de septiembre de 2026",
            "resultado": "1 - 7 - 12 - 28 - 43 - 16",
            "metadata": {"game": "baloto"},
        }
    )

    assert result.draw_number == "12345"
    assert result.draw_date == date(2026, 9, 13)
    assert result.main_numbers == [1, 7, 12, 28, 43]
    assert result.bonus_numbers == [16]
    assert result.source == "baloto-colombia"


def test_revancha_payload_keeps_revancha_provenance():
    result = get_colombia_source_adapter("revancha-colombia").parse_draw(
        {
            "sorteo": 12345,
            "fecha": "2026-09-13",
            "resultado": [3, 8, 17, 29, 41, 9],
        }
    )

    assert result.source == "revancha-colombia"
    assert result.main_numbers == [3, 8, 17, 29, 41]
    assert result.bonus_numbers == [9]


def test_miloto_rejects_bonus_and_out_of_range_numbers():
    adapter = get_colombia_source_adapter("miloto-colombia")

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 123,
                "fecha": "2026-09-13",
                "resultado": [1, 2, 3, 4, 40],
            }
        )

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(
            {
                "sorteo": 123,
                "fecha": "2026-09-13",
                "resultado": [1, 2, 3, 4, 5, 6],
            }
        )


def test_unknown_or_non_string_source_is_fail_closed():
    with pytest.raises(KeyError, match="Unknown lottery source"):
        get_colombia_source_adapter("unknown-colombia")

    with pytest.raises(TypeError, match="Invalid source name"):
        get_colombia_source_adapter(123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source",
    ["", "   ", "bad\nsource", "baloto-colombia\n", "baloto-colombia\t", "a" * 256],
)
def test_source_resolution_rejects_invalid_names(source):
    with pytest.raises(ValueError, match="Invalid source name"):
        get_colombia_source_adapter(source)
