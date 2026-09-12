from __future__ import annotations

import math


def validate_predictions(
    value: object,
    expected_count: int,
    min_confidence_threshold: float = 0.0,
    include_extra_number: bool = False,
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
        extra_number = item.get("extra_number")
        if (
            not isinstance(numbers, list)
            or len(numbers) != 5
            or any(
                isinstance(number, bool)
                or not isinstance(number, int)
                or not 1 <= number <= 1000
                for number in numbers
            )
            or len(set(numbers)) != 5
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not min_confidence_threshold <= confidence <= 100
        ):
            return False
        if include_extra_number:
            if (
                isinstance(extra_number, bool)
                or not isinstance(extra_number, int)
                or not 1 <= extra_number <= 1000
            ):
                return False
        elif extra_number is not None:
            return False
    return True
