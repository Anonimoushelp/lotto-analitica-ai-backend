from app.services.gemini_prompt import build_prediction_prompt


def test_prediction_prompt_requires_superbalota_when_requested():
    prompt = build_prediction_prompt(
        lottery_name="Baloto",
        strategy="balanceado",
        prediction_count=3,
        historical_numbers=[[5, 12, 23, 31, 42]],
        main_number_min=1,
        main_number_max=43,
        include_extra_number=True,
        historical_extra_numbers=[7, 13],
        extra_number_label="Superbalota",
        extra_number_min=1,
        extra_number_max=16,
    )

    assert "extra_number" in prompt
    assert "exactamente un entero de 1 a 16" in prompt
    assert "Histórico de Superbalota: [7,13]" in prompt
    assert "exactamente 5 enteros distintos de 1 a 43" in prompt


def test_prediction_prompt_does_not_require_extra_number_for_games_without_it():
    prompt = build_prediction_prompt(
        lottery_name="MiLoto",
        strategy="balanceado",
        prediction_count=2,
        historical_numbers=[[5, 12, 23, 31, 39]],
        main_number_min=1,
        main_number_max=39,
    )

    assert "extra_number" not in prompt
    assert "exactamente 5 enteros distintos de 1 a 39" in prompt
