from datetime import date

import pytest

from app.integrations.colombia_lotteries import BalotoAdapter, MiLotoAdapter


def test_baloto_parses_official_result_shape():
    result = BalotoAdapter().parse_draw(
        {
            "sorteo": "SORTEO #605",
            "fecha": "Miércoles 9 de Septiembre de 2026",
            "resultado": "05 - 16 - 22 - 36 - 43 - 14",
        }
    )
    assert result.draw_number == "605"
    assert result.draw_date == date(2026, 9, 9)
    assert result.main_numbers == [5, 16, 22, 36, 43]
    assert result.bonus_numbers == [14]
    assert result.source == "baloto-colombia"


def test_miloto_parses_official_result_shape():
    result = MiLotoAdapter().parse_draw(
        {
            "sorteo": "605",
            "fecha": "11 de Septiembre de 2026",
            "resultado": "04 - 17 - 27 - 33 - 36",
        }
    )
    assert result.draw_number == "605"
    assert result.draw_date == date(2026, 9, 11)
    assert result.main_numbers == [4, 17, 27, 33, 36]
    assert result.bonus_numbers is None
    assert result.source == "miloto-colombia"


def test_baloto_rejects_out_of_range_superbalota():
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        BalotoAdapter().parse_draw(
            {
                "sorteo": "605",
                "fecha": "9 de Septiembre de 2026",
                "resultado": "05 - 16 - 22 - 36 - 43 - 17",
            }
        )


def test_miloto_rejects_out_of_range_number():
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        MiLotoAdapter().parse_draw(
            {
                "sorteo": "605",
                "fecha": "11 de Septiembre de 2026",
                "resultado": "04 - 17 - 27 - 33 - 40",
            }
        )


def test_provider_adapters_reject_unexpected_fields():
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        MiLotoAdapter().parse_draw(
            {
                "sorteo": "605",
                "fecha": "11 de Septiembre de 2026",
                "resultado": "04 - 17 - 27 - 33 - 36",
                "url": "https://attacker.invalid",
            }
        )


def test_provider_adapters_reject_duplicate_numbers():
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        BalotoAdapter().parse_draw(
            {
                "sorteo": "605",
                "fecha": "9 de Septiembre de 2026",
                "resultado": "05 - 16 - 16 - 36 - 43 - 14",
            }
        )


@pytest.mark.parametrize(
    "result",
    [
        "05--16-22-36-43-14",
        "05 -  16 - -22 - 36 - 43 - 14",
        "05 -16-22-36-43-14-",
    ],
)
def test_provider_adapters_reject_malformed_number_separators(result: str):
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        BalotoAdapter().parse_draw(
            {
                "sorteo": "605",
                "fecha": "9 de Septiembre de 2026",
                "resultado": result,
            }
        )
