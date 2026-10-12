import pytest

from app.services.gemini_validator import (
    normalize_prediction_risk_levels,
    normalize_risk_level,
    validate_predictions,
)


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        ("Bajo", "Bajo"),
        ("baja", "Bajo"),
        ("Low", "Bajo"),
        ("Medio", "Moderado"),
        ("Media", "Moderado"),
        ("medium", "Moderado"),
        ("moderate", "Moderado"),
        ("Moderado", "Moderado"),
        ("Alto", "Alto"),
        ("high", "Alto"),
        ("riesgo alto", "Alto"),
        (None, "Moderado"),
        ("unexpected model label", "Moderado"),
    ],
)
def test_normalize_risk_level(input_value, expected):
    assert normalize_risk_level(input_value) == expected


def test_normalize_prediction_risk_levels_preserves_other_fields():
    payload = {
        "predictions": [
            {"numbers": [1, 2, 3, 4, 5], "risk_level": "Medio", "custom": "kept"}
        ],
        "other": "kept",
    }

    normalized = normalize_prediction_risk_levels(payload)

    assert normalized["predictions"][0]["risk_level"] == "Moderado"
    assert normalized["predictions"][0]["numbers"] == [1, 2, 3, 4, 5]
    assert normalized["predictions"][0]["custom"] == "kept"
    assert normalized["other"] == "kept"
    assert payload["predictions"][0]["risk_level"] == "Medio"


def test_validate_predictions_accepts_only_normalized_risk_levels():
    valid = {
        "predictions": [
            {
                "numbers": [1, 2, 3, 4, 5],
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }
    invalid = {
        "predictions": [
            {
                "numbers": [1, 2, 3, 4, 5],
                "confidence_score": 82,
                "risk_level": "Medio",
            }
        ]
    }

    assert validate_predictions(valid, expected_count=1)
    assert not validate_predictions(invalid, expected_count=1)


def test_validate_predictions_requires_superbalota_within_official_range():
    valid = {
        "predictions": [
            {
                "numbers": [1, 2, 3, 4, 5],
                "extra_number": 16,
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }
    missing = {
        "predictions": [
            {
                "numbers": [1, 2, 3, 4, 5],
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }
    out_of_range = {
        "predictions": [
            {
                "numbers": [1, 2, 3, 4, 5],
                "extra_number": 17,
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }

    assert validate_predictions(
        valid,
        expected_count=1,
        include_extra_number=True,
        extra_number_min=1,
        extra_number_max=16,
    )
    assert not validate_predictions(
        missing,
        expected_count=1,
        include_extra_number=True,
        extra_number_min=1,
        extra_number_max=16,
    )
    assert not validate_predictions(
        out_of_range,
        expected_count=1,
        include_extra_number=True,
        extra_number_min=1,
        extra_number_max=16,
    )
