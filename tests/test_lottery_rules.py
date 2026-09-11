from app.services.gemini_validator import validate_predictions
from app.services.lottery_rules import get_verified_lottery_rules


def test_verified_rules_cover_supported_lotteries():
    assert get_verified_lottery_rules("miloto") is not None
    assert get_verified_lottery_rules("BALOTO") is not None
    assert get_verified_lottery_rules("Revancha") is not None
    assert get_verified_lottery_rules("unknown") is None


def test_miloto_prediction_contract():
    rules = get_verified_lottery_rules("miloto")
    assert rules is not None
    value = {"predictions": [{"numbers": [1, 10, 20, 30, 39], "confidence_score": 85}]}
    assert validate_predictions(value, 1, rules)
    assert not validate_predictions(
        {"predictions": [{"numbers": [1, 10, 20, 30, 40], "confidence_score": 85}]},
        1,
        rules,
    )


def test_baloto_extra_number_contract():
    rules = get_verified_lottery_rules("baloto")
    assert rules is not None
    valid = {
        "predictions": [
            {"numbers": [1, 10, 20, 30, 43], "extra_number": 16, "confidence_score": 85}
        ]
    }
    assert validate_predictions(valid, 1, rules, include_extra_number=True)
    assert not validate_predictions(
        {"predictions": [{"numbers": [1, 10, 20, 30, 43], "extra_number": 17, "confidence_score": 85}]},
        1,
        rules,
        include_extra_number=True,
    )


def test_extra_number_is_rejected_when_not_requested():
    rules = get_verified_lottery_rules("baloto")
    assert rules is not None
    value = {
        "predictions": [
            {"numbers": [1, 10, 20, 30, 43], "extra_number": 16, "confidence_score": 85}
        ]
    }
    assert not validate_predictions(value, 1, rules, include_extra_number=False)


def test_revancha_uses_the_same_verified_matrix_as_baloto():
    rules = get_verified_lottery_rules("revancha")
    assert rules is not None
    assert rules.main_numbers_count == 5
    assert rules.max_number == 43
    assert rules.has_extra_number is True
    assert rules.extra_number_min == 1
    assert rules.extra_number_max == 16
