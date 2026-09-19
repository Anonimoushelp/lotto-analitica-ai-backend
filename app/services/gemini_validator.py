from __future__ import annotations

import math


def validate_predictions(
    value: object,
    expected_count: int,
    min_confidence_threshold: float = 0.0,
    include_extra_number: bool = False,
    main_count: int = 5,
    main_min: int = 1,
    main_max: int = 1000,
    extra_min: int | None = None,
    extra_max: int | None = None,
) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("predictions"), list):
        return False
    predictions = value["predictions"]
    if len(predictions) != expected_count:
        return False
    if main_count <= 0 or main_min > main_max:
        return False
    for item in predictions:
        if not isinstance(item, dict):
            return False
        numbers = item.get("numbers")
        confidence = item.get("confidence_score")
        extra_number = item.get("extra_number")
        if (
            not isinstance(numbers, list)
            or len(numbers) != main_count
            or any(
                isinstance(number, bool)
                or not isinstance(number, int)
                or not main_min <= number <= main_max
                for number in numbers
            )
            or len(set(numbers)) != main_count
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not min_confidence_threshold <= confidence <= 100
        ):
            return False
        if include_extra_number:
            if (
                extra_min is None
                or extra_max is None
                or extra_min > extra_max
                or isinstance(extra_number, bool)
                or not isinstance(extra_number, int)
                or not extra_min <= extra_number <= extra_max
            ):
                return False
        elif extra_number is not None:
            return False
    return True
