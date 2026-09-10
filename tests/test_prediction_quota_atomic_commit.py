from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.schemas.ai_prediction import AiPredictionRequest
from app.services.prediction_service import PredictionService
from app.services.quota_service import QuotaExceededError
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
        except (QuotaExceededError, Exception):
            pass

        db.commit()
        rows = db.scalars(
            select(TenantQuotaUsage).where(TenantQuotaUsage.tenant_id == tenant_id)
        ).all()
        assert rows == []
