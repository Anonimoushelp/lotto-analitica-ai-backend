from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.models.plan import Plan
from app.models.plan_quota import PlanQuota
from app.models.tenant import Tenant
from app.models.tenant_quota_usage import TenantQuotaUsage
from app.schemas.ai_prediction import AiPredictionRequest
from app.services.prediction_service import PredictionService


def _seed_prediction_context(db: Session, *, prediction_limit: int) -> tuple[int, int]:
    plan = Plan(code=f"prediction-quota-{prediction_limit}", name="Prediction Quota", is_active=True)
    db.add(plan)
    db.flush()
    db.add_all(
        [
            PlanQuota(
                plan_id=plan.id,
                quota_code="ai_generations.monthly",
                limit_value=10,
            ),
            PlanQuota(
                plan_id=plan.id,
                quota_code="predictions.max",
                limit_value=prediction_limit,
            ),
        ]
    )
    tenant = Tenant(
        name="Prediction Quota Tenant",
        slug=f"prediction-quota-{prediction_limit}",
        plan_id=plan.id,
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    lottery = Lottery(
        tenant_id=tenant.id,
        code="PRED-QUOTA",
        name="Prediction Quota Lottery",
        country="CO",
        active=True,
    )
    db.add(lottery)
    db.flush()
    db.add(
        LotteryDraw(
            lottery_id=lottery.id,
            draw_number="D-001",
            draw_date=date(2026, 9, 1),
            main_numbers=[1, 2, 3, 4, 5],
        )
    )
    db.commit()
    return tenant.id, lottery.id


def test_prediction_quota_rejection_happens_before_gemini_call(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id, lottery_id = _seed_prediction_context(db, prediction_limit=0)
        called = False

        def forbidden_gemini(prompt: str):
            nonlocal called
            called = True
            raise AssertionError("Gemini must not be called after quota rejection")

        monkeypatch.setattr(
            "app.services.prediction_service.GeminiClient.generate_json",
            forbidden_gemini,
        )

        payload = AiPredictionRequest(lottery_id=lottery_id, prediction_count=1)
        with pytest.raises(HTTPException) as exc_info:
            PredictionService.generate(db, payload, tenant_id)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "AI generation quota exceeded"
        assert called is False

        db.rollback()
        assert db.scalar(select(TenantQuotaUsage)) is None


def test_prediction_quota_reservation_is_atomic_when_second_quota_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tenant_id, lottery_id = _seed_prediction_context(db, prediction_limit=0)
        called = False

        def forbidden_gemini(prompt: str):
            nonlocal called
            called = True
            raise AssertionError("Gemini must not be called after quota rejection")

        monkeypatch.setattr(
            "app.services.prediction_service.GeminiClient.generate_json",
            forbidden_gemini,
        )

        payload = AiPredictionRequest(lottery_id=lottery_id, prediction_count=1)
        with pytest.raises(HTTPException):
            PredictionService.generate(db, payload, tenant_id)

        db.rollback()
        assert called is False
        assert db.scalar(select(TenantQuotaUsage)) is None
