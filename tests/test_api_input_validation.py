from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.lottery import LotteryCreate, LotteryUpdate
from app.schemas.lottery_draw import LotteryDrawCreate, LotteryDrawUpdate


def test_lottery_create_normalizes_text_fields():
    payload = LotteryCreate(
        code="  TEST001  ",
        name="  Lotería de Prueba  ",
        country="  Colombia  ",
    )

    assert payload.code == "TEST001"
    assert payload.name == "Lotería de Prueba"
    assert payload.country == "Colombia"


@pytest.mark.parametrize("field", ["code", "name", "country"])
def test_lottery_create_rejects_blank_text_fields(field):
    values = {
        "code": "TEST001",
        "name": "Lotería de Prueba",
        "country": "Colombia",
    }
    values[field] = "   "

    with pytest.raises(ValidationError):
        LotteryCreate(**values)


@pytest.mark.parametrize("field", ["code", "name", "country"])
def test_lottery_update_rejects_blank_text_fields(field):
    with pytest.raises(ValidationError):
        LotteryUpdate(**{field: "   "})


def test_draw_create_normalizes_identifiers():
    payload = LotteryDrawCreate(
        lottery_id=1,
        draw_number="  001  ",
        draw_date=date(2026, 9, 16),
        main_numbers=[1, 2, 3],
        source="  official  ",
    )

    assert payload.draw_number == "001"
    assert payload.source == "official"


@pytest.mark.parametrize("field", ["draw_number", "source"])
def test_draw_create_rejects_blank_identifiers(field):
    values = {
        "lottery_id": 1,
        "draw_number": "001",
        "draw_date": date(2026, 9, 16),
        "main_numbers": [1, 2, 3],
        "source": "official",
    }
    values[field] = "   "

    with pytest.raises(ValidationError):
        LotteryDrawCreate(**values)


@pytest.mark.parametrize("field", ["draw_number", "source"])
def test_draw_update_rejects_blank_identifiers(field):
    with pytest.raises(ValidationError):
        LotteryDrawUpdate(**{field: "   "})
