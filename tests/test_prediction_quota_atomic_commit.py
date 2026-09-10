from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.schemas.ai_prediction import AiPredictionRequest
from app.services.prediction_service import PredictionService
from tests.test_prediction_quota_order import _seed_prediction_context


def test_prediction_quota_rejection_does_not_persist_partial_ai_usage_on_commit(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id, lottery_id = _seed_prediction_context(db, prediction_limit=0)

        def forbidden_gemini(prompt: str):
            raise AssertionError("Gemini must not be called after quota rejection")

        monkeypatch.setattr(
            "app.services.prediction_service.GeminiClient.generate_json",
            forbidden_gemini,
        )

        payload = AiPredictionRequest(lottery_id=lottery_id, prediction_count=1)
        try:
            PredictionService.generate(db, payload, tenant_id)
        except HTTPException as exc:
            assert exc.status_code == 429
        else:
            raise AssertionError("Expected prediction quota rejection")

        db.commit()
        rows = db.scalars(
            select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant_id)
        ).all()
        assert rows == []


def test_prediction_quota_provider_failure_does_not_persist_usage_on_commit(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id, lottery_id = _seed_prediction_context(db, prediction_limit=3)

        def failing_gemini(prompt: str):
            raise RuntimeError("simulated provider failure")

        monkeypatch.setattr(
            "app.services.prediction_service.GeminiClient.generate_json",
            failing_gemini,
        )

        payload = AiPredictionRequest(lottery_id=lottery_id, prediction_count=1)
        try:
            PredictionService.generate(db, payload, tenant_id)
        except RuntimeError as exc:
            assert str(exc) == "simulated provider failure"
        else:
            raise AssertionError("Expected Gemini provider failure")

        db.commit()
        rows = db.scalars(
            select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant_id)
        ).all()
        assert rows == []


def test_prediction_quota_validation_failure_does_not_persist_usage_on_commit(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id, lottery_id = _seed_prediction_context(db, prediction_limit=3)

        def invalid_gemini(prompt: str) -> dict:
            return {
                "predictions": [
                    {
                        "numbers": [6, 7, 8, 9],
                        "confidence_score": 87.5,
                    }
                ]
            }

        monkeypatch.setattr(
            "app.services.prediction_service.GeminiClient.generate_json",
            invalid_gemini,
        )

        payload = AiPredictionRequest(lottery_id=lottery_id, prediction_count=1)
        try:
            PredictionService.generate(db, payload, tenant_id)
        except HTTPException as exc:
            assert exc.status_code == 502
            assert exc.detail == (
                "Gemini returned predictions that do not match the required contract"
            )
        else:
            raise AssertionError("Expected Gemini validation failure")

        db.commit()
        rows = db.scalars(
            select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant_id)
        ).all()
        assert rows == []
