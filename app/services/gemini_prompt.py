from __future__ import annotations

import json


def build_prediction_prompt(
    lottery_name: str,
    strategy: str,
    prediction_count: int,
    historical_numbers: list[list[int]],
) -> str:
    history = json.dumps(historical_numbers, separators=(",", ":"))
    return (
        "Actúa como analista estadístico para Lotto Analítica AI. "
        "Analiza únicamente los datos históricos proporcionados; no afirmes "
        "capacidad de predecir el azar. Devuelve JSON válido con una clave "
        "predictions que contenga exactamente la cantidad solicitada. Cada "
        "elemento debe tener numbers (exactamente 5 enteros), confidence_score "
        "entre 0 y 100, risk_level y rationale. "
        f"Lotería: {lottery_name}. Estrategia: {strategy}. "
        f"Cantidad: {prediction_count}. Histórico: {history}"
    )
