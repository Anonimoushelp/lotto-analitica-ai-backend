from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import prediction_service
from app.services.prediction_service import PredictionService


def _setup(monkeypatch, generated):
    captured = {}

    class FakeLottery:
        id = 1
        name = "Test Lottery"
        code = "miloto"

    class FakeDB:
        def get(self, model, lottery_id):
            return FakeLottery()

    class FakeDraw:
        main_numbers = [1, 2, 3, 4, 5]

    monkeypatch.setattr(
        prediction_service.LotteryDrawRepository,
        "list",
        staticmethod(lambda **kwargs: [FakeDraw()]),
    )
    monkeypatch.setattr(
        prediction_service,
        "build_prediction_prompt",
        lambda **kwargs: captured.update(prompt_kwargs=kwargs) or "prompt",
    )
    monkeypatch.setattr(
        prediction_service.GeminiClient,
        "generate_json",
        staticmethod(
            lambda prompt, temperature=0.2: captured.update(
                prompt=prompt, temperature=temperature
            )
            or generated
        ),
    )
    monkeypatch.setattr(
        prediction_service,
        "validate_predictions",
        lambda value, expected_count, rules, include_extra_number=False: True,
    )
    return FakeDB(), captured


def test_generate_passes_requested_temperature(monkeypatch):
    db, captured = _setup(
        monkeypatch,
        {"predictions": [{"numbers": [1, 2, 3, 4, 5], "confidence_score": 85}]},
    )
    payload = SimpleNamespace(
        lottery_id=1,
        strategy="balanceado",
        prediction_count=1,
        temperature=0.7,
        min_confidence_threshold=80,
        include_extra_number=False,
    )

    result = PredictionService.generate(db, payload)

    assert captured["temperature"] == 0.7
    assert result["predictions"][0]["confidence_score"] == 85


def test_generate_rejects_prediction_below_confidence_threshold(monkeypatch):
    db, _ = _setup(
        monkeypatch,
        {"predictions": [{"numbers": [1, 2, 3, 4, 5], "confidence_score": 79}]},
    )
    payload = SimpleNamespace(
        lottery_id=1,
        strategy="balanceado",
        prediction_count=1,
        temperature=0.7,
        min_confidence_threshold=80,
        include_extra_number=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        PredictionService.generate(db, payload)

    assert exc_info.value.status_code == 502
    assert "confidence" in str(exc_info.value.detail).lower()
