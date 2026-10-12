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
        include_extra_number = bool(payload.include_extra_number or uses_superbalota)
        historical_extra_numbers = [
            number
            for draw in draws
            if draw.main_numbers
            for number in (draw.bonus_numbers or [])
            if isinstance(number, int) and not isinstance(number, bool)
        ]
        extra_number_label = "Superbalota" if uses_superbalota else "número adicional"
        extra_number_min = 1
        extra_number_max = 16 if uses_superbalota else 1000

        prompt = build_prediction_prompt(
            lottery_name=lottery.name,
            strategy=payload.strategy,
            prediction_count=payload.prediction_count,
            historical_numbers=historical_numbers,
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
            numbers = sorted(item["numbers"])
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
                    "parity_ratio": f"{even} Par / {len(numbers) - even} Impar",
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
