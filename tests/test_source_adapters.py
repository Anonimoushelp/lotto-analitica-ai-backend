from datetime import date

import pytest

from app.sources.adapters import (
    BalotoAdapter,
    MiLotoAdapter,
    RevanchaAdapter,
    SuperAstroAdapter,
)
from app.sources.normalizer import SourceNormalizationError


def test_miloto_adapter_normalizes_official_shape():
    record = MiLotoAdapter().normalize(
        {
            "draw_number": 609,
            "draw_date": "2026-09-18",
            "main_numbers": [10, 15, 31, 33, 39],
        }
    )

    assert record.lottery_code == "MILOTO"
    assert record.draw_type == "MILOTO"
    assert record.draw_number == "609"
    assert record.draw_date == date(2026, 9, 18)
    assert record.main_numbers == [10, 15, 31, 33, 39]
    assert record.bonus_numbers is None


def test_baloto_adapter_maps_superbalota():
    record = BalotoAdapter().normalize(
        {
            "draw_number": "2026-09-19-B",
            "draw_date": "2026-09-19",
            "main_numbers": [11, 13, 17, 19, 39],
            "superbalota": [4],
        }
    )

    assert record.lottery_code == "BALOTO"
    assert record.draw_type == "BALOTO"
    assert record.main_numbers == [11, 13, 17, 19, 39]
    assert record.bonus_numbers == [4]


def test_revancha_adapter_is_independent_draw_type():
    record = RevanchaAdapter().normalize(
        {
            "draw_number": "2026-09-19-R",
            "draw_date": "2026-09-19",
            "main_numbers": [10, 25, 27, 38, 42],
            "revancha_bonus": [3],
        }
    )

    assert record.lottery_code == "REVANCHA"
    assert record.draw_type == "REVANCHA"
    assert record.main_numbers == [10, 25, 27, 38, 42]
    assert record.bonus_numbers == [3]


def test_super_astro_sol_preserves_four_digit_result_and_sign():
    record = SuperAstroAdapter().normalize(
        {
            "draw_type": "ASTRO_SOL",
            "draw_number": 5534,
            "draw_date": "2026-09-19",
            "number": "8874",
            "metadata": {"sign": "Cancer"},
        }
    )

    assert record.lottery_code == "SUPER_ASTRO"
    assert record.draw_type == "ASTRO_SOL"
    assert record.main_numbers == [8874]
    assert record.metadata["raw_result"] == "8874"
    assert record.metadata["digit_count"] == 4
    assert record.metadata["sign"] == "Cancer"


def test_super_astro_preserves_leading_zero():
    record = SuperAstroAdapter().normalize(
        {
            "draw_type": "ASTRO_LUNA",
            "draw_number": 8241,
            "draw_date": "2026-09-12",
            "number": "0982",
        }
    )

    assert record.main_numbers == [982]
    assert record.metadata["raw_result"] == "0982"


@pytest.mark.parametrize("draw_type", ["DEFAULT", "ASTRO", ""])
def test_super_astro_rejects_invalid_draw_type(draw_type):
    with pytest.raises(SourceNormalizationError, match="draw_type"):
        SuperAstroAdapter().normalize(
            {
                "draw_type": draw_type,
                "draw_number": 1,
                "draw_date": "2026-09-21",
                "number": "1234",
            }
        )


def test_super_astro_rejects_non_four_digit_result():
    with pytest.raises(SourceNormalizationError, match="four digits"):
        SuperAstroAdapter().normalize(
            {
                "draw_type": "ASTRO_SOL",
                "draw_number": 1,
                "draw_date": "2026-09-21",
                "number": "123",
            }
        )
