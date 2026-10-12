from types import SimpleNamespace

import pytest

from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.schemas.ai_prediction import AiPredictionRequest
from app.services.gemini_client import GeminiClient
from app.services.gemini_prompt import build_prediction_prompt
from app.services.gemini_validator import validate_predictions
from app.services.prediction_service import PredictionService


def test_four_digit_prompt_requests_one_result_not_five_balls():
    prompt = build_prediction_prompt(
        lottery_name="Lotería de Manizales",
        strategy="balanceado",
        prediction_count=3,
        historical_numbers=[[18], [2025], [982]],
        main_number_min=0,
        main_number_max=9999,
        main_number_count=1,
        single_number_mode=True,
    )

    assert "exactamente un entero entre 0 y 9999" in prompt
    assert "no generes cinco bolas" in prompt
    assert "el cliente completará los ceros iniciales" in prompt


def test_validator_accepts_one_four_digit_result_including_leading_zero_value():
    value = {
        "predictions": [
            {
                "numbers": [7],
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }

    assert validate_predictions(
        value,
        expected_count=1,
        main_number_min=0,
        main_number_max=9999,
        main_number_count=1,
    )


@pytest.mark.parametrize("numbers", [[1, 23], [1, 23, 456, 789]])
def test_validator_rejects_multiple_values_for_four_digit_single_result(numbers):
    value = {
        "predictions": [
            {
                "numbers": numbers,
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }

    assert not validate_predictions(
        value,
        expected_count=1,
        main_number_min=0,
        main_number_max=9999,
        main_number_count=1,
    )


def test_validator_rejects_four_digit_result_outside_range():
    value = {
        "predictions": [
            {
                "numbers": [10000],
                "confidence_score": 82,
                "risk_level": "Moderado",
            }
        ]
    }

    assert not validate_predictions(
        value,
        expected_count=1,
        main_number_min=0,
        main_number_max=9999,
        main_number_count=1,
    )


@pytest.mark.parametrize(
    ("code", "name"),
    [
        ("LOTERIA_MANIZALES", "Lotería de Manizales"),
        ("SUPER_ASTRO", "Super Astro"),
        ("CHONTICO", "Chontico"),
    ],
)
def test_prediction_service_returns_one_four_digit_ticket(
    monkeypatch,
    code,
    name,
):
    lottery = SimpleNamespace(id=5, code=code, name=name)
    draws = [
        SimpleNamespace(
            main_numbers=[18],
            bonus_numbers=None,
            metadata_json={"raw_result": "0018", "digit_count": 4},
        ),
        SimpleNamespace(
            main_numbers=[2025],
            bonus_numbers=None,
            metadata_json={"raw_result": "2025", "digit_count": 4},
        ),
        SimpleNamespace(
            main_numbers=[982],
            bonus_numbers=None,
            metadata_json={"raw_result": "0982", "digit_count": 4},
        ),
    ]
    db = SimpleNamespace(get=lambda model, record_id: lottery)
    prompts = []

    def fake_generate_json(prompt):
        prompts.append(prompt)
        return {
            "predictions": [
                {
                    "numbers": [7],
                    "confidence_score": 82,
                    "risk_level": "Moderado",
                    "rationale": "Resultado de cuatro cifras basado en el histórico.",
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
            lottery_id=5,
            prediction_count=1,
            include_extra_number=False,
        ),
    )

    prediction = response["predictions"][0]
    assert prediction["numbers"] == [7]
    assert prediction["parity_ratio"] == "No aplica a un resultado único de cuatro cifras"
    assert "exactamente un entero entre 0 y 9999" in prompts[0]


def test_baloto_and_miloto_keep_five_ball_contract(monkeypatch):
    for lottery, draws, expected_prompt in [
        (
            SimpleNamespace(id=17, code="BALOTO", name="Baloto"),
            [SimpleNamespace(main_numbers=[5, 12, 23, 31, 42], bonus_numbers=[7])],
            "exactamente 5 enteros distintos de 1 a 43",
        ),
        (
            SimpleNamespace(id=16, code="MILOTO", name="MiLoto"),
            [SimpleNamespace(main_numbers=[5, 12, 23, 31, 39], bonus_numbers=None)],
            "exactamente 5 enteros distintos de 1 a 39",
        ),
    ]:
        db = SimpleNamespace(get=lambda model, record_id, lottery=lottery: lottery)

        def fake_generate_json(prompt, expected_prompt=expected_prompt, lottery=lottery):
            assert expected_prompt in prompt
            values = [1, 9, 20, 31, 42] if lottery.code == "BALOTO" else [1, 9, 20, 31, 39]
            prediction = {
                "numbers": values,
                "confidence_score": 82,
                "risk_level": "Moderado",
                "rationale": "Fixture válido.",
            }
            if lottery.code == "BALOTO":
                prediction["extra_number"] = 8
            return {"predictions": [prediction]}

        monkeypatch.setattr(
            LotteryDrawRepository,
            "list",
            staticmethod(lambda selected_draws=draws, **kwargs: selected_draws),
        )
        monkeypatch.setattr(GeminiClient, "generate_json", staticmethod(fake_generate_json))
        monkeypatch.setattr(
            PredictionService,
            "model_status",
            staticmethod(lambda: {"model_name": "test-model", "version": "test", "status": "IDLE"}),
        )

        response = PredictionService.generate(
            db=db,
            payload=AiPredictionRequest(
                lottery_id=lottery.id,
                prediction_count=1,
                include_extra_number=False,
            ),
        )
        assert len(response["predictions"][0]["numbers"]) == 5
