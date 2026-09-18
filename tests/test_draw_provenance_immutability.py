from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services.lottery_draw_service import LotteryDrawService


def _draw(source="baloto-colombia"):
    return SimpleNamespace(
        id=7,
        lottery_id=1,
        draw_number="D-1",
        draw_date=date(2026, 9, 1),
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=[6],
        source=source,
        metadata_json={"provider": source},
    )


def test_update_rejects_provenance_source_replacement(monkeypatch):
    draw = _draw()
    monkeypatch.setattr(LotteryDrawService, "get_draw", staticmethod(lambda db, draw_id: draw))

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=object(),
            draw_id=draw.id,
            update_data={"source": "revancha-colombia"},
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Lottery draw source is immutable"
    assert draw.source == "baloto-colombia"


def test_update_allows_same_source_without_rewriting_provenance(monkeypatch):
    draw = _draw()
    monkeypatch.setattr(LotteryDrawService, "get_draw", staticmethod(lambda db, draw_id: draw))
    monkeypatch.setattr(LotteryDrawService, "_commit_update_for_test", None, raising=False)

    class DB:
        def get(self, model, lottery_id):
            return object()

        def commit(self):
            pass

        def refresh(self, value):
            pass

    class Repo:
        @staticmethod
        def get_by_number(**kwargs):
            return None

        @staticmethod
        def get_by_date(**kwargs):
            return None

    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        Repo.get_by_number,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_date",
        Repo.get_by_date,
    )

    result = LotteryDrawService.update_draw(
        db=DB(),
        draw_id=draw.id,
        update_data={"source": "  baloto-colombia  "},
    )

    assert result is draw
    assert draw.source == "baloto-colombia"


def test_update_without_source_preserves_existing_provenance(monkeypatch):
    draw = _draw()
    monkeypatch.setattr(LotteryDrawService, "get_draw", staticmethod(lambda db, draw_id: draw))

    class DB:
        def get(self, model, lottery_id):
            return object()

        def commit(self):
            pass

        def refresh(self, value):
            pass

    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=None),
    )

    result = LotteryDrawService.update_draw(
        db=DB(),
        draw_id=draw.id,
        update_data={"draw_number": "D-2"},
    )

    assert result is draw
    assert draw.source == "baloto-colombia"
    assert draw.draw_number == "D-2"


def test_update_collision_is_scoped_to_same_source(monkeypatch):
    draw = _draw(source="baloto-colombia")
    monkeypatch.setattr(LotteryDrawService, "get_draw", staticmethod(lambda db, draw_id: draw))

    class DB:
        def get(self, model, lottery_id):
            return object()

        def commit(self):
            pass

        def refresh(self, value):
            pass

    get_by_number = Mock(return_value=None)
    get_by_date = Mock(return_value=None)
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        get_by_number,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_date",
        get_by_date,
    )

    result = LotteryDrawService.update_draw(
        db=DB(),
        draw_id=draw.id,
        update_data={"draw_number": "D-2", "draw_date": date(2026, 9, 2)},
    )

    assert result is draw
    assert draw.source == "baloto-colombia"
    assert get_by_number.call_args.kwargs["source"] == "baloto-colombia"
    assert get_by_date.call_args.kwargs["source"] == "baloto-colombia"
    assert get_by_number.call_args.kwargs["source"] == "baloto-colombia"
    assert get_by_date.call_args.kwargs["source"] == "baloto-colombia"
