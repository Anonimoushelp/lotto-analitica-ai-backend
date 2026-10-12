from __future__ import annotations

from typing import Any

ALLOWED_RISK_LEVELS = {"Bajo", "Moderado", "Alto"}

_RISK_LEVEL_ALIASES = {
    "bajo": "Bajo",
    "baja": "Bajo",
    "low": "Bajo",
    "low risk": "Bajo",
    "riesgo bajo": "Bajo",
    "moderado": "Moderado",
    "moderada": "Moderado",
    "medio": "Moderado",
    "media": "Moderado",
    "medium": "Moderado",
    "moderate": "Moderado",
    "medium risk": "Moderado",
    "moderate risk": "Moderado",
    "riesgo medio": "Moderado",
    "riesgo moderado": "Moderado",
    "alto": "Alto",
    "alta": "Alto",
    "high": "Alto",
    "high risk": "Alto",
    "riesgo alto": "Alto",
}


def normalize_risk_level(value: object) -> str:
    """Map common model labels to the response schema's allowed risk values."""
    if not isinstance(value, str):
        return "Moderado"

    normalized = " ".join(
        value.strip().casefold().replace("_", " ").replace("-", " ").split()
    )
    return _RISK_LEVEL_ALIASES.get(normalized, "Moderado")


def normalize_prediction_risk_levels(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize risk levels before Pydantic validates the API response."""
    predictions = value.get("predictions")
    if not isinstance(predictions, list):
        return value

    normalized_predictions = []
    for item in predictions:
        if isinstance(item, dict):
            normalized_item = dict(item)
            normalized_item["risk_level"] = normalize_risk_level(
                normalized_item.get("risk_level")
            )
            normalized_predictions.append(normalized_item)
        else:
            normalized_predictions.append(item)

    normalized_value = dict(value)
    normalized_value["predictions"] = normalized_predictions
    return normalized_value


def validate_predictions(
    value: object,
    expected_count: int,
    *,
    include_extra_number: bool = False,
    main_number_min: int = 1,
    main_number_max: int = 1000,
    extra_number_min: int = 1,
    extra_number_max: int = 1000,
) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("predictions"), list):
        return False
    predictions = value["predictions"]
    if len(predictions) != expected_count:
        return False
    for item in predictions:
        if not isinstance(item, dict):
            return False
        numbers = item.get("numbers")
        confidence = item.get("confidence_score")
        if (
            not isinstance(numbers, list)
            or len(numbers) != 5
            or any(
                not isinstance(number, int)
                or isinstance(number, bool)
                or not main_number_min <= number <= main_number_max
                for number in numbers
            )
            or len(set(numbers)) != 5
            or not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 100
            or item.get("risk_level") not in ALLOWED_RISK_LEVELS
        ):
            return False

        if include_extra_number:
            extra_number = item.get("extra_number")
            if (
                not isinstance(extra_number, int)
                or isinstance(extra_number, bool)
                or not extra_number_min <= extra_number <= extra_number_max
            ):
                return False
    return True
