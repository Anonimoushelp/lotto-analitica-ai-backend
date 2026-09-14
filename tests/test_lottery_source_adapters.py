from datetime import date

import pytest
from pydantic import ValidationError

from app.integrations.lottery_source_adapters import (
    JsonLotterySourceAdapter,
    LotterySourceAdapterRegistry,
)


def valid_payload() -> dict:
    return {
        "draw_number": "2026-001",
        "draw_date": date(2026, 9, 13),
        "main_numbers": [5, 12, 23, 31, 42],
        "bonus_numbers": [7],
        "metadata": {"provider_draw_id": "abc-123"},
    }


def test_json_adapter_normalizes_source_and_preserves_data():
    adapter = JsonLotterySourceAdapter("provider-example")

    result = adapter.parse_draw(valid_payload())

    assert result.source == "provider-example"
    assert result.draw_number == "2026-001"
    assert result.main_numbers == [5, 12, 23, 31, 42]
    assert result.metadata == {"provider_draw_id": "abc-123"}


def test_json_adapter_rejects_mismatched_source():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["source"] = "other-provider"

    with pytest.raises(ValueError, match="source does not match"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_unknown_provider_fields():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["unexpected"] = "reject-me"

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_non_object_payload():
    adapter = JsonLotterySourceAdapter("provider-example")

    with pytest.raises(ValueError, match="payload must be an object"):
        adapter.parse_draw([1, 2, 3])


def test_json_adapter_rejects_invalid_canonical_numbers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["main_numbers"] = [0, 12, 23]

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_duplicate_numbers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["main_numbers"] = [5, 12, 12, 31, 42]

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_duplicate_bonus_numbers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["bonus_numbers"] = [7, 7]

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_control_characters_in_source_name():
    with pytest.raises(ValueError, match="Invalid source name"):
        JsonLotterySourceAdapter("provider\nexample")


def test_json_adapter_rejects_control_characters_in_payload_identifiers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["draw_number"] = "2026-001\t"

    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_registry_requires_unique_explicit_sources():
    first = JsonLotterySourceAdapter("provider-a")
    second = JsonLotterySourceAdapter("provider-a")
    registry = LotterySourceAdapterRegistry([first])

    with pytest.raises(ValueError, match="already registered"):
        registry.register(second)


def test_registry_does_not_resolve_unknown_source():
    registry = LotterySourceAdapterRegistry(
        [JsonLotterySourceAdapter("provider-a")]
    )

    with pytest.raises(KeyError, match="Unknown lottery source"):
        registry.get("provider-b")


def test_registry_rejects_non_string_lookup():
    registry = LotterySourceAdapterRegistry(
        [JsonLotterySourceAdapter("provider-a")]
    )

    with pytest.raises(ValueError, match="Invalid source name"):
        registry.get(123)  # type: ignore[arg-type]


def test_canonical_validation_error_is_not_exposed():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["main_numbers"] = []

    with pytest.raises(ValueError) as exc_info:
        adapter.parse_draw(payload)

    assert "provider_draw_id" not in str(exc_info.value)
    assert "ValidationError" not in str(exc_info.value)
