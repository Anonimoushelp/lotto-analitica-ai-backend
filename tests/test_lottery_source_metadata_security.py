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
    for index in range(7):
        value["level"] = {}
        value = value["level"]

    with pytest.raises(ValidationError, match="Metadata nesting is too deep"):
        LotteryDrawPayload.model_validate(_payload(nested))


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
