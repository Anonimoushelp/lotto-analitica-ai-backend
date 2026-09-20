import json

import pytest
from pydantic import ValidationError

from app.schemas.statistics import StatisticalOverviewResponse


def test_statistical_overview_serializes_to_json_without_non_json_values():
    payload = StatisticalOverviewResponse(
        module_status="READY",
        algorithms_count=6,
        draws_analyzed=10,
    )

    encoded = payload.model_dump_json()
    decoded = json.loads(encoded)

    assert decoded == {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 10,
    }
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


@pytest.mark.parametrize("status", ["ready", "UNKNOWN", "", None])
def test_statistical_overview_rejects_invalid_status(status):
    with pytest.raises(ValidationError):
        StatisticalOverviewResponse(
            module_status=status,
            algorithms_count=6,
            draws_analyzed=10,
        )


@pytest.mark.parametrize("field", ["algorithms_count", "draws_analyzed"])
def test_statistical_overview_rejects_negative_counts(field):
    values = {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 10,
    }
    values[field] = -1

    with pytest.raises(ValidationError):
        StatisticalOverviewResponse(**values)


def test_statistical_overview_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        StatisticalOverviewResponse(module_status="READY", algorithms_count=6)


def test_statistical_overview_rejects_extra_fields():
    with pytest.raises(ValidationError):
        StatisticalOverviewResponse(
            module_status="READY",
            algorithms_count=6,
            draws_analyzed=10,
            unexpected="synthetic",
        )
