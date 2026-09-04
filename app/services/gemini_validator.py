from __future__ import annotations


def validate_predictions(value: object, expected_count: int) -> bool:
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
            or any(not isinstance(number, int) or not 1 <= number <= 1000 for number in numbers)
            or len(set(numbers)) != 5
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 100
        ):
            return False
    return True
