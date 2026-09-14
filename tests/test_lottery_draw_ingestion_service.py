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
    get_number = Mock(return_value=duplicate)
    get_date = Mock(return_value=duplicate)
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        get_number,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        get_date,
    )

    result = service.ingest(db, 10, payload())

    assert result is duplicate
    create_draw.assert_not_called()
    get_number.assert_called_once_with(
        db=db, lottery_id=10, draw_number="1001", source="provider-example"
    )
    get_date.assert_called_once_with(
        db=db, lottery_id=10, draw_date=date(2026, 9, 13), source="provider-example"
    )


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


def test_ingestion_scopes_idempotency_by_source(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-b")
    create_draw = Mock(return_value="created")
    service = LotteryDrawIngestionService(adapter, create_draw=create_draw)
    existing_from_other_source = existing(source="provider-a")
    get_number = Mock(return_value=None)
    get_date = Mock(return_value=None)
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        get_number,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        get_date,
    )

    result = service.ingest(db, 10, payload())

    assert result == "created"
    assert existing_from_other_source.source == "provider-a"
    get_number.assert_called_once_with(
        db=db, lottery_id=10, draw_number="1001", source="provider-b"
    )
    get_date.assert_called_once_with(
        db=db, lottery_id=10, draw_date=date(2026, 9, 13), source="provider-b"
    )
    create_draw.assert_called_once()


def test_ingestion_retries_are_idempotent(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-example")
    created = existing()
    create_draw = Mock(return_value=created)
    service = LotteryDrawIngestionService(adapter, create_draw=create_draw)
    get_number = Mock(side_effect=[None, created])
    get_date = Mock(side_effect=[None, created])
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        get_number,
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        get_date,
    )

    first = service.ingest(db, 10, payload())
    second = service.ingest(db, 10, payload())

    assert first is created
    assert second is created
    create_draw.assert_called_once()


def test_ingestion_rejects_ambiguous_number_or_date_conflict(monkeypatch):
    db = Mock()
    adapter = JsonLotterySourceAdapter("provider-example")
    service = LotteryDrawIngestionService(adapter, create_draw=Mock())
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=existing()),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=existing(main_numbers=[1, 2, 3, 4, 5])),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.ingest(db, 10, payload())

    assert exc_info.value.status_code == 409


def test_ingestion_rejects_unknown_provider_fields():
    adapter = JsonLotterySourceAdapter("provider-example")
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload(untrusted_url="https://example.invalid"))
