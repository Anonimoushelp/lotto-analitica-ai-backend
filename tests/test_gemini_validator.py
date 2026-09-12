import math

from app.services.gemini_validator import validate_predictions


def _prediction(confidence=80, extra_number=None):
    return {
        "numbers": [1, 2, 3, 4, 5],
        "confidence_score": confidence,
        "extra_number": extra_number,
    }


def test_validator_rejects_boolean_main_numbers():
    item = _prediction()
    item["numbers"] = [True, 2, 3, 4, 5]
    assert not validate_predictions({"predictions": [item]}, 1)


def test_validator_rejects_non_finite_confidence():
    assert not validate_predictions({"predictions": [_prediction(math.nan)]}, 1)
    assert not validate_predictions({"predictions": [_prediction(math.inf)]}, 1)


def test_validator_enforces_confidence_threshold():
    assert not validate_predictions(
        {"predictions": [_prediction(79)]},
        1,
        min_confidence_threshold=80,
    )
    assert validate_predictions(
        {"predictions": [_prediction(80)]},
        1,
        min_confidence_threshold=80,
    )


def test_validator_rejects_unrequested_extra_number():
    assert not validate_predictions(
        {"predictions": [_prediction(extra_number=7)]},
        1,
        include_extra_number=False,
    )


def test_validator_accepts_generic_extra_number_when_explicitly_requested():
    assert validate_predictions(
        {"predictions": [_prediction(extra_number=7)]},
        1,
        include_extra_number=True,
    )
