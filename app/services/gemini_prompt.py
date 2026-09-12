from __future__ import annotations

import json

from app.services.lottery_rules import LotteryRules


def build_prediction_prompt(
    lottery_name: str,
    strategy: str,
    prediction_count: int,
    historical_numbers: list[list[int]],
    rules: LotteryRules,
    include_extra_number: bool = False,
) -> str:
    history = json.dumps(historical_numbers, separators=(",", ":"))
    extra_instruction = (
        f" Include extra_number as exactly one integer from {rules.extra_number_min} to {rules.extra_number_max}."
        if include_extra_number and rules.has_extra_number
        else " Do not include extra_number."
    )
    return (
        "Actúa como analista estadístico para Lotto Analítica AI. "
        "Analiza únicamente los datos históricos proporcionados; no afirmes "
        "capacidad de predecir el azar. Devuelve JSON válido con una clave "
        "predictions que contenga exactamente la cantidad solicitada. Cada "
        f"elemento debe tener numbers (exactamente {rules.main_numbers_count} enteros "
        f"entre {rules.min_number} y {rules.max_number}, sin repetidos), "
        "confidence_score entre 0 y 100, risk_level y rationale."
        f"{extra_instruction} "
        f"Lotería: {lottery_name}. Estrategia: {strategy}. "
        f"Cantidad: {prediction_count}. Histórico: {history}"
    )
