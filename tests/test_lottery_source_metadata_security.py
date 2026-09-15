from datetime import date

import pytest
from pydantic import ValidationError

from app.integrations.lottery_sources import LotteryDrawPayload


def _payload(metadata):
    return {
        "draw_number": "123",
        "draw_date": date(2026, 9, 13),
        "main_numbers": [1, 2, 3, 4, 5],
        "source": "test-source",
        "metadata": metadata,
    }


def test_metadata_rejects_control_characters_recursively():
    with pytest.raises(ValidationError, match="Metadata contains invalid characters"):
        LotteryDrawPayload.model_validate(_payload({"provider": {"label": "ok\nno"}}))


def test_metadata_rejects_control_characters_in_keys():
    with pytest.raises(ValidationError, match="Metadata contains invalid characters"):
        LotteryDrawPayload.model_validate(_payload({"provider\tname": "value"}))


def test_metadata_rejects_excessive_nesting():
    nested = value = {}
    for _ in range(7):
        value["level"] = {}
        value = value["level"]

    with pytest.raises(ValidationError, match="Metadata nesting is too deep"):
        LotteryDrawPayload.model_validate(_payload(nested))


def test_metadata_rejects_oversized_string_values():
    with pytest.raises(ValidationError, match="Metadata strings are too long"):
        LotteryDrawPayload.model_validate(
            _payload({"provider_response": "x" * 513})
        )


def test_metadata_rejects_oversized_keys():
    with pytest.raises(ValidationError, match="Metadata keys are too long"):
        LotteryDrawPayload.model_validate(_payload({"k" * 129: "value"}))


def test_metadata_rejects_too_many_nodes():
    metadata = {f"item_{index}": index for index in range(256)}
    with pytest.raises(ValidationError, match="Metadata contains too many nodes"):
        LotteryDrawPayload.model_validate(_payload(metadata))


def test_metadata_rejects_unsupported_value_types():
    with pytest.raises(ValidationError, match="Metadata contains unsupported value types"):
        LotteryDrawPayload.model_validate(_payload({"payload": {"binary": b"secret"}}))


def test_metadata_rejects_non_finite_numbers():
    with pytest.raises(ValidationError, match="Metadata contains non-finite numbers"):
        LotteryDrawPayload.model_validate(_payload({"score": float("nan")}))


def test_metadata_rejects_non_json_collections():
    with pytest.raises(ValidationError, match="Metadata contains unsupported value types"):
        LotteryDrawPayload.model_validate(_payload({"tags": ("result", "draw")}))


def test_metadata_allows_safe_json_scalar_types():
    result = LotteryDrawPayload.model_validate(
        _payload(
            {
                "provider": "official",
                "request": {"page": 1, "enabled": True, "score": 0.5},
                "empty": None,
            }
        )
    )

    assert result.metadata["request"]["enabled"] is True
    assert result.metadata["request"]["score"] == 0.5


def test_metadata_allows_safe_nested_provider_context():
    result = LotteryDrawPayload.model_validate(
        _payload(
            {
                "provider": "official",
                "request": {"page": 1, "tags": ["result", "draw"]},
            }
        )
    )

    assert result.metadata["request"]["tags"] == ["result", "draw"]
