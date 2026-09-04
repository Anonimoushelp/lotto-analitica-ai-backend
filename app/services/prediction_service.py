from collections import Counter
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.lottery import Lottery
from app.repositories.lottery_draw_repository import LotteryDrawRepository


class PredictionService:
    @staticmethod
    def model_status() -> dict[str, str]:
        configured = bool(getattr(settings, "gemini_api_key", ""))
        return {
            "model_name": "Lotto-Net Gemini AI Core",
            "version": "2.5-pro-ready" if configured else "not-configured",
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

        frequency = Counter(
            number
            for draw in draws
            for number in (draw.main_numbers or [])
        )
        ranked = [number for number, _ in frequency.most_common()]
        if not ranked:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The selected lottery has no main numbers available",
            )

        predictions = []
        for index in range(payload.prediction_count):
            numbers = []
            for offset in range(len(ranked)):
                candidate = ranked[(index * 2 + offset) % len(ranked)]
                if candidate not in numbers:
                    numbers.append(candidate)
                if len(numbers) == 5:
                    break

            numbers.sort()
            even = sum(number % 2 == 0 for number in numbers)
            confidence = min(
                98.0,
                max(
                    payload.min_confidence_threshold,
                    70.0 + (sum(frequency[n] for n in numbers) / len(numbers)),
                ),
            )
            risk = (
                "Bajo"
                if payload.strategy == "conservador"
                else "Alto"
                if payload.strategy == "agresivo"
                else "Moderado"
            )
            predictions.append(
                {
                    "id": f"ai-pred-{payload.lottery_id}-{index + 1}",
                    "numbers": numbers,
                    "extra_number": None,
                    "confidence_score": round(confidence, 2),
                    "risk_level": risk,
                    "pattern_detected": "Frecuencia histórica y dispersión",
                    "rationale": "Combinación generada exclusivamente con el histórico real disponible en el backend; no representa una garantía de resultado futuro.",
                    "expected_sum": sum(numbers),
                    "parity_ratio": f"{even} Par / {len(numbers) - even} Impar",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        top = ranked[:5]
        cold = sorted(
            ranked,
            key=lambda number: (
                next(
                    (index for index, draw in enumerate(draws) if number in (draw.main_numbers or [])),
                    -1,
                ),
                frequency[number],
            ),
        )[:4]
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
                    "id": "ins-frequency",
                    "pattern_name": "Concentración de frecuencia histórica",
                    "category": "Frecuencia",
                    "weight_percentage": 100.0,
                    "status": "Detectado",
                    "description": "Los números recomendados se seleccionan por frecuencia observada en los últimos 100 sorteos disponibles.",
                }
            ],
            "model_status": model_status,
        }
