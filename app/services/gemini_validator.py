from __future__ import annotations

from app.services.lottery_rules import LotteryRules


def validate_predictions(
    value: object,
    expected_count: int,
    rules: LotteryRules,
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
        if (
            not isinstance(numbers, list)
            or len(numbers) != rules.main_numbers_count
            or any(
                not isinstance(number, int)
                or not rules.min_number <= number <= rules.max_number
                for number in numbers
            )
            or len(set(numbers)) != rules.main_numbers_count
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 100
        ):
            return False

        extra_number = item.get("extra_number")
        if include_extra_number:
            if (
                not rules.has_extra_number
                or rules.extra_number_min is None
                or rules.extra_number_max is None
                or not isinstance(extra_number, int)
                or not rules.extra_number_min <= extra_number <= rules.extra_number_max
                or extra_number in numbers
            ):
                return False
        elif extra_number is not None:
            return False
    return True
