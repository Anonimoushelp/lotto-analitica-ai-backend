import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService


class FakeSession:
    def __init__(self, lottery=None, draw=None):
        self.lottery = lottery
        self.draw = draw
        self.rollback_calls = 0
        self.commit_calls = 0
        self.refresh_calls = 0

    def get(self, model, object_id):
        if model.__name__ == "Lottery":
            return self.lottery
        if model.__name__ == "LotteryDraw":
            return self.draw
        return None

    def commit(self):
        self.commit_calls += 1
        raise IntegrityError("statement", {}, Exception("unique violation"))

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, value):
        self.refresh_calls += 1


def test_create_draw_maps_concurrent_unique_conflict(monkeypatch):
    lottery = object()
    db = FakeSession(lottery=lottery)

    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_date",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.create",
        lambda **kwargs: (_ for _ in ()).throw(
            IntegrityError("statement", {}, Exception("unique violation"))
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        LotteryDrawService.create_draw(
            db=db,
            lottery_id=1,
            draw_number="100",
            draw_date="2026-09-04",
            main_numbers=[1, 2, 3, 4, 5],
            source="test-source",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Lottery draw conflicts with an existing record"


def test_update_draw_rolls_back_on_concurrent_unique_conflict(monkeypatch):
    draw = LotteryDraw(
        id=7,
        lottery_id=1,
        draw_number="100",
        draw_date="2026-09-04",
        source="test-source",
    )
    db = FakeSession(lottery=object(), draw=draw)

    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_date",
        lambda **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=7,
            update_data={"draw_number": "101"},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Lottery draw conflicts with an existing record"
    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert db.refresh_calls == 0
