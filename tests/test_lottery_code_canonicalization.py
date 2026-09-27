from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.models.lottery import Lottery
from app.services.lottery_service import LotteryService


def test_create_canonicalizes_lottery_code(monkeypatch):
    created = Lottery(
        id=1,
        code="loteria_risaralda",
        name="Lotería de Risaralda",
        country="Colombia",
        active=True,
    )
    monkeypatch.setattr(
        "app.services.lottery_service.LotteryRepository.get_by_code",
        lambda **_: None,
    )
    monkeypatch.setattr(
        "app.services.lottery_service.LotteryRepository.create",
        lambda **_: created,
    )

    result = LotteryService.create_lottery(
        db=Mock(),
        payload={
            "code": "  LOTERIA_RISARALDA  ",
            "name": "Lotería de Risaralda",
            "country": "Colombia",
            "active": True,
        },
    )

    assert result.code == "loteria_risaralda"


def test_update_rejects_canonical_code_collision(monkeypatch):
    current = Lottery(id=1, code="loteria_risaralda", name="R", country="Colombia")
    other = Lottery(id=2, code="loteria_cundinamarca", name="C", country="Colombia")
    monkeypatch.setattr(
        "app.services.lottery_service.LotteryService.get_lottery",
        lambda **_: current,
    )
    monkeypatch.setattr(
        "app.services.lottery_service.LotteryRepository.get_by_code",
        lambda **_: other,
    )

    with pytest.raises(HTTPException) as exc:
        LotteryService.update_lottery(
            db=Mock(),
            lottery_id=1,
            update_data={"code": " LOTERIA_CUNDINAMARCA "},
        )

    assert exc.value.status_code == 409
