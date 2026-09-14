from datetime import UTC, date, datetime

import pytest

from app.integrations.lottery_source_adapters import (
    JsonLotterySourceAdapter,
    LotterySourceAdapterRegistry,
)
from app.integrations.lottery_sources import LotteryDrawPayload


def valid_payload() -> dict:
    return {
        "draw_number": "2026-001",
        "draw_date": date(2026, 9, 13),
        "main_numbers": [5, 12, 23, 31, 42],
        "bonus_numbers": [7],
        "metadata": {"provider_draw_id": "abc-123"},
    }


def test_json_adapter_normalizes_source_and_preserves_data():
    adapter = JsonLotterySourceAdapter(" provider-example ")
    result = adapter.parse_draw(valid_payload())
    assert result.source == "provider-example"
    assert result.draw_number == "2026-001"
    assert result.main_numbers == [5, 12, 23, 31, 42]
    assert result.metadata == {"provider_draw_id": "abc-123"}


def test_json_adapter_normalizes_identifier_whitespace():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["draw_number"] = " 2026-001 "
    result = adapter.parse_draw(payload)
    assert result.draw_number == "2026-001"


@pytest.mark.parametrize("value", [123, 7.5, True, None, ["2026-001"]])
def test_json_adapter_rejects_non_string_draw_number(value):
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["draw_number"] = value
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


@pytest.mark.parametrize("value", [123, 7.5, True, None, ["provider-example"]])
def test_json_adapter_rejects_non_string_source(value):
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["source"] = value
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


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
    with pytest.raises(TypeError, match="payload must be an object"):
        adapter.parse_draw([1, 2, 3])


@pytest.mark.parametrize(
    "numbers",
    [
        [0, 12, 23],
        [5, 12, 12, 31, 42],
        ["5", 12, 23, 31, 42],
        [1.0, 12, 23, 31, 42],
        [True, 12, 23, 31, 42],
        [1_000_001, 12, 23],
    ],
)
def test_json_adapter_rejects_invalid_main_numbers(numbers):
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["main_numbers"] = numbers
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_duplicate_bonus_numbers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["bonus_numbers"] = [7, 7]
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_bonus_overlap_with_main_numbers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["bonus_numbers"] = [12]
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_oversized_bonus_number():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["bonus_numbers"] = [1_000_001]
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_rejects_datetime_draw_date():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["draw_date"] = datetime(2026, 9, 13, 12, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_json_adapter_accepts_calendar_date():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    result = adapter.parse_draw(payload)
    assert result.draw_date == date(2026, 9, 13)


def test_json_adapter_rejects_control_characters_in_source_name():
    with pytest.raises(ValueError, match="Invalid source name"):
        JsonLotterySourceAdapter("provider\nexample")


def test_json_adapter_rejects_control_characters_in_payload_identifiers():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["draw_number"] = "2026-001\t"
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw(payload)


def test_registry_rejects_control_characters_in_adapter_source():
    with pytest.raises(ValueError, match="Invalid source name"):
        LotterySourceAdapterRegistry(
            [JsonLotterySourceAdapter("provider-example")]
        ).register(type("Adapter", (), {"source_name": "bad\nsource"})())


def test_registry_rejects_non_adapter_objects():
    with pytest.raises(TypeError, match="must implement parse_draw"):
        LotterySourceAdapterRegistry().register(
            type("Adapter", (), {"source_name": "provider-example"})()
        )


def test_registry_rejects_non_normalized_adapter_source():
    adapter = type(
        "Adapter",
        (),
        {
            "source_name": " provider-example ",
            "parse_draw": lambda self, payload: payload,
        },
    )()
    with pytest.raises(ValueError, match="must be normalized"):
        LotterySourceAdapterRegistry().register(adapter)


def test_registry_rejects_oversized_adapter_source():
    adapter = type(
        "Adapter",
        (),
        {
            "source_name": "a" * 256,
            "parse_draw": lambda self, payload: payload,
        },
    )()
    with pytest.raises(ValueError, match="Invalid source name"):
        LotterySourceAdapterRegistry().register(adapter)


def test_registry_requires_unique_explicit_sources():
    first = JsonLotterySourceAdapter("provider-a")
    second = JsonLotterySourceAdapter("provider-a")
    registry = LotterySourceAdapterRegistry([first])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(second)


def test_registry_does_not_resolve_unknown_source():
    registry = LotterySourceAdapterRegistry([JsonLotterySourceAdapter("provider-a")])
    with pytest.raises(KeyError, match="Unknown lottery source"):
        registry.get("provider-b")


def test_registry_rejects_non_string_lookup():
    registry = LotterySourceAdapterRegistry([JsonLotterySourceAdapter("provider-a")])
    with pytest.raises(TypeError, match="Invalid source name"):
        registry.get(123)  # type: ignore[arg-type]


def test_registry_parse_draw_enforces_canonical_output():
    registry = LotterySourceAdapterRegistry([JsonLotterySourceAdapter("provider-a")])
    result = registry.parse_draw("provider-a", valid_payload())
    assert isinstance(result, LotteryDrawPayload)
    assert result.source == "provider-a"


def test_registry_parse_draw_rejects_invalid_adapter_output():
    adapter = type(
        "Adapter",
        (),
        {
            "source_name": "provider-a",
            "parse_draw": lambda self, payload: payload,
        },
    )()
    registry = LotterySourceAdapterRegistry([adapter])
    with pytest.raises(TypeError, match="invalid draw payload"):
        registry.parse_draw("provider-a", valid_payload())


def test_registry_parse_draw_rejects_mismatched_adapter_output():
    other = JsonLotterySourceAdapter("provider-b")
    adapter = type(
        "Adapter",
        (),
        {
            "source_name": "provider-a",
            "parse_draw": lambda self, payload: other.parse_draw(payload),
        },
    )()
    registry = LotterySourceAdapterRegistry([adapter])
    with pytest.raises(ValueError, match="mismatched source"):
        registry.parse_draw("provider-a", valid_payload())


def test_canonical_validation_error_is_not_exposed():
    adapter = JsonLotterySourceAdapter("provider-example")
    payload = valid_payload()
    payload["main_numbers"] = []
    with pytest.raises(ValueError) as exc_info:
        adapter.parse_draw(payload)
    assert "provider_draw_id" not in str(exc_info.value)
    assert "ValidationError" not in str(exc_info.value)
