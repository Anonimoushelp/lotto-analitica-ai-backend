from datetime import date

import pytest

from app.sources.parsers import SourceParseError
from app.sources.provider_parsers import (
    BalotoFamilyJsonParser,
    MiLotoJsonParser,
    SuperAstroJsonParser,
)


def test_miloto_parser_extracts_canonical_payload() -> None:
    payload = MiLotoJsonParser().parse_record(
        {
            "sorteo": 609,
            "fecha": "2026-09-18",
            "result": [10, 15, 31, 33, 39],
        }
    )

    assert payload["draw_type"] == "MILOTO"
    assert payload["draw_number"] == 609
    assert payload["draw_date"] == "2026-09-18"
    assert payload["main_numbers"] == [10, 15, 31, 33, 39]


@pytest.mark.parametrize(
    ("game_type", "bonus_key", "draw_type"),
    [
        ("BALOTO", "superbalota", "BALOTO"),
        ("REVANCHA", "revancha_bonus", "REVANCHA"),
    ],
)
def test_baloto_family_requires_explicit_game_type(
    game_type: str, bonus_key: str, draw_type: str
) -> None:
    payload = BalotoFamilyJsonParser().parse_record(
        {
            "game_type": game_type,
            "draw_number": 123,
            "draw_date": date(2026, 9, 19).isoformat(),
            "main_numbers": [11, 13, 17, 19, 39],
            bonus_key: [4],
        }
    )

    assert payload["draw_type"] == draw_type
    assert payload["bonus_numbers"] == [4]


def test_baloto_family_rejects_implicit_row_order() -> None:
    with pytest.raises(SourceParseError, match="game_type"):
        BalotoFamilyJsonParser().parse_record(
            {
                "draw_number": 123,
                "draw_date": "2026-09-19",
                "main_numbers": [11, 13, 17, 19, 39],
                "superbalota": [4],
            }
        )


def test_super_astro_parser_preserves_leading_zero_and_sign() -> None:
    payload = SuperAstroJsonParser().parse_record(
        {
            "tipo": "ASTRO_LUNA",
            "sorteo": 8241,
            "fecha": "2026-09-12",
            "resultado": "0982",
            "sign": "Libra",
        }
    )

    assert payload["draw_type"] == "ASTRO_LUNA"
    assert payload["number"] == "0982"
    assert payload["metadata"]["raw_result"] == "0982"
    assert payload["metadata"]["digit_count"] == 4
    assert payload["metadata"]["sign"] == "Libra"


@pytest.mark.parametrize("value", ["982", "12345", "12A4"])
def test_super_astro_parser_rejects_invalid_result(value: str) -> None:
    with pytest.raises(SourceParseError, match="four digits"):
        SuperAstroJsonParser().parse_record(
            {
                "draw_type": "ASTRO_SOL",
                "draw_number": 1,
                "draw_date": "2026-09-21",
                "number": value,
            }
        )
