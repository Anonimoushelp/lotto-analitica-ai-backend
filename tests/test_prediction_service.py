from types import SimpleNamespace

import pytest

from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.schemas.ai_prediction import AiPredictionRequest
from app.services.gemini_client import GeminiClient
from app.services.prediction_service import PredictionService


@pytest.mark.parametrize(
    ("lottery_id", "code", "name"),
    [
        (17, "BALOTO", "Baloto"),
        (18, "REVANCHA", "Baloto Revancha"),
    ],
)
def test_prediction_service_includes_superbalota_for_baloto_family(
    monkeypatch,
    lottery_id,
    code,
    name,
):
    lottery = SimpleNamespace(id=lottery_id, code=code, name=name)
    draws = [
        SimpleNamespace(
            main_numbers=[5, 12, 23, 31, 42],
            bonus_numbers=[7],
        ),
        SimpleNamespace(
            main_numbers=[4, 8, 20, 21, 39],
            bonus_numbers=[13],
        ),
    ]
    db = SimpleNamespace(get=lambda model, record_id: lottery)
    prompts = []

    def fake_generate_json(prompt):
        prompts.append(prompt)
        return {
            "predictions": [
                {
                    "numbers": [1, 9, 20, 31, 42],
                    "extra_number": 8,
                    "confidence_score": 76,
                    "risk_level": "Moderado",
                    "rationale": "Combinación basada en el histórico disponible.",
                }
            ]
        }

    monkeypatch.setattr(
        LotteryDrawRepository,
        "list",
        staticmethod(lambda **kwargs: draws),
    )
    monkeypatch.setattr(
        GeminiClient,
        "generate_json",
        staticmethod(fake_generate_json),
    )
    monkeypatch.setattr(
        PredictionService,
        "model_status",
        staticmethod(
            lambda: {
                "model_name": "test-model",
                "version": "test",
                "status": "IDLE",
            }
        ),
    )

    response = PredictionService.generate(
        db=db,
        payload=AiPredictionRequest(
            lottery_id=lottery_id,
            prediction_count=1,
            include_extra_number=False,
        ),
    )

    assert response["predictions"][0]["numbers"] == [1, 9, 20, 31, 42]
    assert response["predictions"][0]["extra_number"] == 8
    assert "numbers (exactamente 5 enteros distintos de 1 a 43)" in prompts[0]
    assert "extra_number" in prompts[0]
    assert "Histórico de Superbalota: [7,13]" in prompts[0]
    assert "exactamente un entero de 1 a 16" in prompts[0]


def test_prediction_service_does_not_require_extra_number_for_miloto(
    monkeypatch,
):
    lottery = SimpleNamespace(id=3, code="MILOTO", name="MiLoto")
    draws = [
        SimpleNamespace(
            main_numbers=[5, 12, 23, 31, 39],
            bonus_numbers=None,
        ),
    ]
    db = SimpleNamespace(get=lambda model, record_id: lottery)
    prompts = []

    def fake_generate_json(prompt):
        prompts.append(prompt)
        return {
            "predictions": [
                {
                    "numbers": [1, 9, 20, 31, 39],
                    "confidence_score": 76,
                    "risk_level": "Moderado",
                    "rationale": "Combinación basada en el histórico disponible.",
                }
            ]
        }

    monkeypatch.setattr(
        LotteryDrawRepository,
        "list",
        staticmethod(lambda **kwargs: draws),
    )
    monkeypatch.setattr(
        GeminiClient,
        "generate_json",
        staticmethod(fake_generate_json),
    )
    monkeypatch.setattr(
        PredictionService,
        "model_status",
        staticmethod(
            lambda: {
                "model_name": "test-model",
                "version": "test",
                "status": "IDLE",
            }
        ),
    )

    response = PredictionService.generate(
        db=db,
        payload=AiPredictionRequest(
            lottery_id=3,
            prediction_count=1,
            include_extra_number=False,
        ),
    )

    assert response["predictions"][0]["extra_number"] is None
    assert "numbers (exactamente 5 enteros distintos de 1 a 39)" in prompts[0]
    assert "extra_number" not in prompts[0]
