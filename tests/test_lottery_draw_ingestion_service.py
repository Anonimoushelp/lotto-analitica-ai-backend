from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.integrations.lottery_source_adapters import JsonLotterySourceAdapter
from app.services.lottery_draw_ingestion_service import LotteryDrawIngestionService


def payload(**overrides):
    value = {
        "draw_number": "1001",
        "draw_date": date(2026, 9, 13),
        "main_numbers": [4, 11, 22, 35, 41],
        "bonus_numbers": [7],
        "metadata": {"provider": "fixture"},
    }
    value.update(overrides)
    return value


def existing(**overrides):
    value = {
        "draw_number": "1001",
        "draw_date": date(2026, 9, 13),
        "main_numbers": [4, 11, 22, 35, 41],
        "bonus_numbers": [7],
        "source": "provider-example",
        "metadata_json": {"provider": "fixture"},
    }
    value.update(overrides)
    return SimpleNamespace(**value)


def test_ingestion_persists_canonical_payload(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-example")
    create_draw = Mock(return_value="created")
    service = LotteryDrawIngestionService(adapter, create_draw=create_draw)
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=None),
    )

    result = service.ingest(db, 10, payload())

    assert result == "created"
    create_draw.assert_called_once_with(
        db=db,
        lottery_id=10,
        draw_number="1001",
        draw_date=date(2026, 9, 13),
        main_numbers=[4, 11, 22, 35, 41],
        bonus_numbers=[7],
        source="provider-example",
        metadata_json={"provider": "fixture"},
    )


def test_ingestion_is_idempotent_for_exact_duplicate(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-example")
    create_draw = Mock()
    service = LotteryDrawIngestionService(adapter, create_draw=create_draw)
    duplicate = existing()
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=duplicate),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=duplicate),
    )

    result = service.ingest(db, 10, payload())

    assert result is duplicate
    create_draw.assert_not_called()


def test_ingestion_rejects_conflicting_duplicate(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-example")
    service = LotteryDrawIngestionService(adapter, create_draw=Mock())
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=existing(main_numbers=[1, 2, 3, 4, 5])),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.ingest(db, 10, payload())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Lottery draw conflicts with an existing record"


def test_ingestion_rejects_metadata_conflict(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-example")
    service = LotteryDrawIngestionService(adapter, create_draw=Mock())
    existing_draw = existing(metadata_json={"provider": "different-fixture"})
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=existing_draw),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=existing_draw),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.ingest(db, 10, payload())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Lottery draw conflicts with an existing record"


def test_ingestion_rejects_unknown_provider_fields():
    adapter = JsonLotterySourceAdapter("provider-example")
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload(untrusted_url="https://example.invalid"))
