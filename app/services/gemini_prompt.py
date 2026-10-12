from __future__ import annotations

import json


def build_prediction_prompt(
    lottery_name: str,
    strategy: str,
    prediction_count: int,
    historical_numbers: list[list[int]],
    *,
    main_number_min: int = 1,
    main_number_max: int = 1000,
    main_number_count: int = 5,
    single_number_mode: bool = False,
    include_extra_number: bool = False,
    historical_extra_numbers: list[int] | None = None,
    extra_number_label: str = "número adicional",
    extra_number_min: int = 1,
    extra_number_max: int = 1000,
) -> str:
    history = json.dumps(historical_numbers, separators=(",", ":"))
    if single_number_mode:
        number_requirement = (
            "numbers (una lista con exactamente un entero entre 0 y 9999 "
            "que representa un único resultado de cuatro cifras; no generes "
            "cinco bolas ni una combinación de números. el cliente completará "
            "los ceros iniciales al mostrar el resultado: 7 se verá como 0007)"
        )
    else:
        number_requirement = (
            f"numbers (exactamente {main_number_count} enteros distintos de "
            f"{main_number_min} a {main_number_max})"
        )
    required_fields = (
        f"{number_requirement}, confidence_score entre 0 y 100, "
        "risk_level y rationale"
    )
    extra_history_text = ""
    if include_extra_number:
        extra_history = json.dumps(
            historical_extra_numbers or [],
            separators=(",", ":"),
        )
        required_fields += (
            f", extra_number (exactamente un entero de "
            f"{extra_number_min} a {extra_number_max})"
        )
        extra_history_text = (
            f" Histórico de {extra_number_label}: {extra_history}."
        )

    return (
        "Actúa como analista estadístico para Lotto Analítica AI. "
        "Analiza únicamente los datos históricos proporcionados; no afirmes "
        "capacidad de predecir el azar. Devuelve JSON válido con una clave "
        "predictions que contenga exactamente la cantidad solicitada. Cada "
        f"elemento debe tener {required_fields}. "
        "risk_level DEBE ser exactamente uno de estos tres valores: "
        '"Bajo", "Moderado" o "Alto". No uses "Medio", "Media", '
        '"Low", "Medium", "High" ni otros valores para risk_level. '
        f"Lotería: {lottery_name}. Estrategia: {strategy}. "
        f"Cantidad: {prediction_count}. Histórico de números principales: "
        f"{history}.{extra_history_text}"
    )
