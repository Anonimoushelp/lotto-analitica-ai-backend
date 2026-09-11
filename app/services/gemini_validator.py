from app.services.lottery_rules import LotteryRules


_LEGACY_RULES = LotteryRules(
    main_numbers_count=5,
    min_number=1,
    max_number=1000,
    has_extra_number=False,
)


def validate_predictions(
    value: object,
    expected_count: int,
    rules: LotteryRules | None = None,
    include_extra_number: bool = False,
) -> bool:
    """Validate predictions using verified lottery rules.

    ``rules`` remains optional for backward compatibility with the original
    generic validator contract. Production callers should always provide the
    verified rules resolved for the target lottery.
    """
    effective_rules = rules or _LEGACY_RULES

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
            or len(numbers) != effective_rules.main_numbers_count
            or any(
                not isinstance(number, int)
                or not effective_rules.min_number <= number <= effective_rules.max_number
                for number in numbers
            )
            or len(set(numbers)) != effective_rules.main_numbers_count
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 100
        ):
            return False

        extra_number = item.get("extra_number")
        if include_extra_number:
            if (
                not effective_rules.has_extra_number
                or effective_rules.extra_number_min is None
                or effective_rules.extra_number_max is None
                or not isinstance(extra_number, int)
                or not effective_rules.extra_number_min <= extra_number <= effective_rules.extra_number_max
                or extra_number in numbers
            ):
                return False
        elif extra_number is not None:
            return False
    return True
