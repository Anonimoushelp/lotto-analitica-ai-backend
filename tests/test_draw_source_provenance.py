from datetime import date
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.lottery_draw import LotteryDrawCreate, LotteryDrawUpdate
from app.services.lottery_draw_service import LotteryDrawService


def test_draw_create_requires_source():
    with pytest.raises(ValidationError):
        LotteryDrawCreate(
            lottery_id=1,
            draw_number="1001",
            draw_date=date(2026, 9, 14),
            main_numbers=[1, 2, 3, 4, 5],
        )


def test_draw_update_rejects_empty_source():
    with pytest.raises(ValidationError):
        LotteryDrawUpdate(source=" ")


def test_create_draw_rejects_empty_source():
    db = Mock()
    db.get.return_value = Mock()

    with pytest.raises(HTTPException) as exc_info:
        LotteryDrawService.create_draw(
            db=db,
            lottery_id=1,
            draw_number="1001",
            draw_date=date(2026, 9, 14),
            main_numbers=[1, 2, 3, 4, 5],
            source=" ",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Lottery draw source is required"


def test_update_draw_rejects_null_source(monkeypatch):
    draw = Mock(
        id=1,
        lottery_id=1,
        draw_number="1001",
        draw_date=date(2026, 9, 14),
        source="provider",
    )
    monkeypatch.setattr(LotteryDrawService, "get_draw", Mock(return_value=draw))
    db = Mock()

    with pytest.raises(HTTPException) as exc_info:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=1,
            update_data={"source": None},
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Lottery draw source is required"
