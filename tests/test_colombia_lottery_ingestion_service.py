from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.integrations.lottery_source_adapters import JsonLotterySourceAdapter
from app.services.colombia_lottery_ingestion_service import (
    ColombiaLotteryIngestionService,
)


def payload(**overrides):
    value = {
        "sorteo": "Sorteo #1001",
        "fecha": "13 de septiembre de 2026",
        "resultado": [4, 11, 22, 35, 41, 7],
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
        "source": "baloto-colombia",
    }
    value.update(overrides)
    return SimpleNamespace(**value)


def test_facade_resolves_explicit_baloto_source_and_ingests(monkeypatch):
    db = Mock()
    created = object()
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawService.create_draw",
        Mock(return_value=created),
    )

    result = ColombiaLotteryIngestionService().ingest(
        db, 10, "baloto-colombia", payload()
    )

    assert result is created


def test_facade_preserves_provider_provenance(monkeypatch):
    db = Mock()
    create_draw = Mock(return_value="created")
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawService.create_draw",
        create_draw,
    )

    ColombiaLotteryIngestionService().ingest(db, 10, "revancha-colombia", payload())

    create_draw.assert_called_once()
    assert create_draw.call_args.kwargs["source"] == "revancha-colombia"


def test_facade_is_idempotent_for_existing_exact_draw(monkeypatch):
    db = Mock()
    duplicate = existing()
    create_draw = Mock()
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=duplicate),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=duplicate),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawService.create_draw",
        create_draw,
    )

    result = ColombiaLotteryIngestionService().ingest(
        db, 10, "baloto-colombia", payload()
    )

    assert result is duplicate
    create_draw.assert_not_called()


def test_facade_rejects_unknown_source_before_persistence():
    with pytest.raises(KeyError, match="Unknown lottery source"):
        ColombiaLotteryIngestionService().ingest(
            Mock(), 10, "untrusted-source", payload()
        )


def test_facade_rejects_non_string_source_before_persistence():
    with pytest.raises(TypeError, match="Invalid source name"):
        ColombiaLotteryIngestionService().ingest(Mock(), 10, 123, payload())


def test_facade_rejects_malformed_provider_payload():
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        ColombiaLotteryIngestionService().ingest(
            Mock(), 10, "miloto-colombia", payload(resultado=[1, 2, 3])
        )


def test_facade_uses_only_explicit_registry_resolution(monkeypatch):
    registry = Mock()
    adapter = JsonLotterySourceAdapter("fixture-source")
    registry.get.return_value = adapter
    service = ColombiaLotteryIngestionService(registry=registry)
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_number",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawRepository.get_by_date",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.lottery_draw_ingestion_service.LotteryDrawService.create_draw",
        Mock(return_value="created"),
    )

    result = service.ingest(
        Mock(),
        10,
        "fixture-source",
        {
            "draw_number": "1",
            "draw_date": date(2026, 9, 13),
            "main_numbers": [1],
            "source": "fixture-source",
        },
    )

    assert result == "created"
    registry.get.assert_called_once_with("fixture-source")
