from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.contracts import RawDrawRecord


class FakeSession:
    def __init__(self, lottery):
        self.lottery = lottery

    def scalar(self, statement):
        return self.lottery


def _record(numbers: list[int]) -> RawDrawRecord:
    return RawDrawRecord(
        lottery_code="TEST001",
        draw_type="DEFAULT",
        draw_number="PRUEBA-001",
        draw_date=date(2026, 9, 24),
        draw_time=None,
        main_numbers=numbers,
        source_name="test-source",
        source_url="https://example.test/results",
        source_timestamp=datetime(2026, 9, 24, 23, 55, tzinfo=UTC),
        metadata={"source_verified": True},
    )


def test_persist_raw_record_is_idempotent_for_exact_repeat(monkeypatch):
    lottery = Lottery(id=1, code="TEST001", name="Test Lottery")
    existing = LotteryDraw(
        id=7,
        lottery_id=1,
        draw_type="DEFAULT",
        draw_number="PRUEBA-001",
        draw_date=date(2026, 9, 24),
        draw_time=None,
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=None,
        source="test-source",
        source_url="https://example.test/results",
        source_timestamp=datetime(2026, 9, 24, 23, 55, tzinfo=UTC),
        metadata_json={"source_verified": True},
    )
    db = FakeSession(lottery)

    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        lambda **kwargs: existing,
    )

    result = LotteryDrawService.persist_raw_record(db=db, record=_record([1, 2, 3, 4, 5]))

    assert result is existing


def test_persist_raw_record_rejects_conflicting_repeat(monkeypatch):
    lottery = Lottery(id=1, code="TEST001", name="Test Lottery")
    existing = LotteryDraw(
        id=7,
        lottery_id=1,
        draw_type="DEFAULT",
        draw_number="PRUEBA-001",
        draw_date=date(2026, 9, 24),
        draw_time=None,
        main_numbers=[1, 2, 3, 4, 5],
        bonus_numbers=None,
        source="test-source",
        source_url="https://example.test/results",
        source_timestamp=datetime(2026, 9, 24, 23, 55, tzinfo=UTC),
        metadata_json={"source_verified": True},
    )
    db = FakeSession(lottery)

    monkeypatch.setattr(
        "app.services.lottery_draw_service.LotteryDrawRepository.get_by_number",
        lambda **kwargs: existing,
    )

    with pytest.raises(HTTPException) as exc_info:
        LotteryDrawService.persist_raw_record(db=db, record=_record([1, 2, 3, 4, 6]))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Conflicting draw payload for an existing lottery/draw identity"
    )
