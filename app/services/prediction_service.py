# ruff: noqa: I001
from collections import Counter
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.lottery import Lottery
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.services.gemini_client import GeminiClient
from app.services.gemini_prompt import build_prediction_prompt
from app.services.gemini_validator import (
    normalize_prediction_risk_levels,
    validate_predictions,
)


# These games draw a single four-digit ticket result rather than five balls.
# Codes match the catalog seeded by Lotto Analítica AI and the four-digit
# provider adapters. The historical-shape fallback below supports future
# single-result games even when their code is not yet registered here.
FOUR_DIGIT_LOTTERY_CODES = {
    "LOTERIA_CUNDINAMARCA",
    "LOTERIA_TOLIMA",
    "LOTERIA_CRUZ_ROJA",
    "LOTERIA_HUILA",
    "LOTERIA_MANIZALES",
    "LOTERIA_VALLE",
    "LOTERIA_META",
    "LOTERIA_BOGOTA",
    "LOTERIA_QUINDIO",
    "LOTERIA_MEDELLIN",
    "LOTERIA_SANTANDER",
    "LOTERIA_RISARALDA",
    "LOTERIA_BOYACA",
    "LOTERIA_CAUCA",
    "EXTRA_COLOMBIA",
    "SUPER_ASTRO",
    "ANTIOQUENITA",
    "CHONTICO",
    "DORADO",
    "CAFETERITO",
    "PAISITA",
    "FANTASTICA",
}


def _has_four_digit_history(draws) -> bool:
    for draw in draws:
        metadata = getattr(draw, "metadata_json", None)
        if not isinstance(metadata, dict):
            continue
        if metadata.get("digit_count") == 4:
            return True
        raw_result = metadata.get("raw_result")
        if isinstance(raw_result, str) and len(raw_result) == 4 and raw_result.isdigit():
            return True
    return False


def _is_single_four_digit_result(
    lottery_code: str,
    lottery_name: str,
    draws,
    historical_numbers: list[list[int]],
) -> bool:
    if lottery_code in FOUR_DIGIT_LOTTERY_CODES:
        return True
    if lottery_code.startswith("LOTERIA_") or "lotería" in lottery_name:
        return True
    if _has_four_digit_history(draws):
        return True

    # An unknown game whose historical draws consistently contain one value
    # is a single-result game, not a five-ball combination.
    if historical_numbers:
        single_result_draws = sum(len(numbers) == 1 for numbers in historical_numbers)
        return single_result_draws / len(historical_numbers) >= 0.8
    return False


class PredictionService:
    @staticmethod
    def model_status() -> dict[str, str]:
        configured = bool(getattr(settings, "gemini_api_key", ""))
        return {
            "model_name": "Lotto-Net Gemini AI Core",
            "version": GeminiClient.MODEL if configured else "not-configured",
            "status": "IDLE" if configured else "UNAVAILABLE",
        }

    @staticmethod
    def generate(db: Session, payload) -> dict:
        lottery = db.get(Lottery, payload.lottery_id)
        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )

        draws = LotteryDrawRepository.list(
            db=db,
            lottery_id=payload.lottery_id,
            limit=100,
        )
        if not draws:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The selected lottery has no historical draws available",
            )

        historical_numbers = [
            draw.main_numbers or []
            for draw in draws
            if draw.main_numbers
        ]
        if not historical_numbers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The selected lottery has no main numbers available",
            )

        lottery_code = (getattr(lottery, "code", "") or "").strip().upper()
        lottery_name = (lottery.name or "").strip().casefold()
        uses_superbalota = (
            lottery_code in {"BALOTO", "REVANCHA"}
            or "baloto" in lottery_name
            or "revancha" in lottery_name
        )
        is_miloto = lottery_code == "MILOTO" or "miloto" in lottery_name
        is_single_four_digit = (
            not uses_superbalota
            and not is_miloto
            and _is_single_four_digit_result(
                lottery_code,
                lottery_name,
                draws,
                historical_numbers,
            )
        )

        include_extra_number = bool(payload.include_extra_number or uses_superbalota)
        historical_extra_numbers = [
            number
            for draw in draws
            if draw.main_numbers
            for number in (draw.bonus_numbers or [])
            if isinstance(number, int) and not isinstance(number, bool)
        ]

        if uses_superbalota:
            main_number_min, main_number_max = 1, 43
            main_number_count = 5
        elif is_miloto:
            main_number_min, main_number_max = 1, 39
            main_number_count = 5
        elif is_single_four_digit:
            main_number_min, main_number_max = 0, 9999
            main_number_count = 1
        else:
            # Retain the existing fallback for any unregistered multi-ball game.
            main_number_min, main_number_max = 1, 1000
            main_number_count = 5

        extra_number_label = "Superbalota" if uses_superbalota else "número adicional"
        extra_number_min = 1
        extra_number_max = 16 if uses_superbalota else 1000

        prompt = build_prediction_prompt(
            lottery_name=lottery.name,
            strategy=payload.strategy,
            prediction_count=payload.prediction_count,
            historical_numbers=historical_numbers,
            main_number_min=main_number_min,
            main_number_max=main_number_max,
            main_number_count=main_number_count,
            single_number_mode=is_single_four_digit,
            include_extra_number=include_extra_number,
            historical_extra_numbers=historical_extra_numbers,
            extra_number_label=extra_number_label,
            extra_number_min=extra_number_min,
            extra_number_max=extra_number_max,
        )
        generated = GeminiClient.generate_json(prompt)
        generated = normalize_prediction_risk_levels(generated)
        if not validate_predictions(
            generated,
            payload.prediction_count,
            include_extra_number=include_extra_number,
            main_number_min=main_number_min,
            main_number_max=main_number_max,
            main_number_count=main_number_count,
            extra_number_min=extra_number_min,
            extra_number_max=extra_number_max,
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned predictions that do not match the required contract",
            )

        frequency = Counter(
            number
            for numbers in historical_numbers
            for number in numbers
        )
        ranked = [number for number, _ in frequency.most_common()]
        predictions = []
        for index, item in enumerate(generated["predictions"]):
            numbers = item["numbers"] if is_single_four_digit else sorted(item["numbers"])
            even = sum(number % 2 == 0 for number in numbers)
            predictions.append(
                {
                    "id": f"ai-pred-{payload.lottery_id}-{index + 1}",
                    "numbers": numbers,
                    "extra_number": item.get("extra_number"),
                    "confidence_score": round(float(item["confidence_score"]), 2),
                    "risk_level": item["risk_level"],
                    "pattern_detected": item.get("pattern_detected", "Análisis Gemini"),
                    "rationale": item.get(
                        "rationale",
                        "Análisis generado por Gemini a partir del histórico real disponible en el backend; no representa una garantía de resultado futuro.",
                    ),
                    "expected_sum": sum(numbers),
                    "parity_ratio": (
                        "No aplica a un resultado único de cuatro cifras"
                        if is_single_four_digit
                        else f"{even} Par / {len(numbers) - even} Impar"
                    ),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        top = ranked[:5]
        cold = sorted(frequency, key=lambda number: (frequency[number], number))[:4]
        model_status = PredictionService.model_status()
        return {
            "summary": {
                "lottery_id": str(lottery.id),
                "lottery_name": lottery.name,
                "active_model": model_status["model_name"],
                "model_version": model_status["version"],
                "overall_confidence": predictions[0]["confidence_score"],
                "top_recommended_numbers": top,
                "cold_recovery_candidates": cold,
                "recommended_strategy": payload.strategy,
                "last_updated": datetime.now(UTC).isoformat(),
            },
            "predictions": predictions,
            "insights": [
                {
                    "id": "ins-gemini",
                    "pattern_name": "Análisis de patrones con Gemini",
                    "category": "IA",
                    "weight_percentage": 100.0,
                    "status": "Detectado",
                    "description": "Gemini analiza el histórico real proporcionado por el backend y devuelve predicciones estructuradas.",
                }
            ],
            "model_status": model_status,
        }
