from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.main import app
from app.schemas.ai_prediction import AiPatternInsight, AiPredictionRequest
from app.services.gemini_validator import validate_predictions
from app.services.statistical_service import StatisticalService

client = TestClient(app)


@pytest.fixture(autouse=True)
def authenticated_read_context():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin", is_active=True)
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def test_statistical_overview_contract(monkeypatch):
    monkeypatch.setattr(StatisticalService, "overview", lambda db: {"module_status": "READY", "algorithms_count": 6, "draws_analyzed": 42})
    response = client.get("/api/v1/statistics/overview")
    assert response.status_code == 200
    assert response.json() == {"module_status": "READY", "algorithms_count": 6, "draws_analyzed": 42}


def test_statistical_service_advanced_algorithms_are_deterministic():
    draws = [
        SimpleNamespace(id=1, draw_date=date(2026, 1, 1), main_numbers=[1, 2, 3, 4, 5]),
        SimpleNamespace(id=2, draw_date=date(2026, 1, 2), main_numbers=[1, 2, 3, 6, 8]),
    ]
    result = StatisticalService.analyze(draws)
    assert result["number_frequency"] == {1: 2, 2: 2, 3: 2, 4: 1, 5: 1, 6: 1, 8: 1}
    assert result["number_recency"] == {1: {"last_seen_draw": 2, "draws_since_seen": 0}, 2: {"last_seen_draw": 2, "draws_since_seen": 0}, 3: {"last_seen_draw": 2, "draws_since_seen": 0}, 4: {"last_seen_draw": 1, "draws_since_seen": 1}, 5: {"last_seen_draw": 1, "draws_since_seen": 1}, 6: {"last_seen_draw": 2, "draws_since_seen": 0}, 8: {"last_seen_draw": 2, "draws_since_seen": 0}}
    assert result["even_odd_distribution"] == {"2-3": 1, "3-2": 1}
    assert result["sum_distribution"] == {"count": 2, "minimum": 15, "maximum": 20, "average": 17.5}
    assert result["pair_frequency"]["1-2"] == 2
    assert result["pair_frequency"]["2-3"] == 2
    assert result["pair_frequency"]["4-5"] == 1
    assert result["consecutive_numbers"] == {"draws_with_consecutive": 2, "total_consecutive_pairs": 6, "maximum_consecutive_pairs": 4}


def test_statistical_service_invariants_hold_for_multiple_draw_sizes():
    draws = [
        SimpleNamespace(id=3, draw_date=date(2026, 1, 3), main_numbers=[1, 3, 5]),
        SimpleNamespace(id=1, draw_date=date(2026, 1, 1), main_numbers=[2, 4, 6]),
        SimpleNamespace(id=2, draw_date=date(2026, 1, 2), main_numbers=[1, 2, 3]),
    ]
    result = StatisticalService.analyze(draws)
    frequency = result["number_frequency"]
    parity = result["even_odd_distribution"]
    sums = result["sum_distribution"]
    recency = result["number_recency"]
    pairs = result["pair_frequency"]
    consecutive = result["consecutive_numbers"]
    assert sum(frequency.values()) == 9
    assert sum(parity.values()) == 3
    assert all(sum(map(int, key.split("-"))) == 3 for key in parity)
    assert sums == {"count": 3, "minimum": 6, "maximum": 12, "average": 9.0}
    assert len(pairs) <= 9
    assert pairs["1-2"] == 1
    assert pairs["1-3"] == 2
    assert pairs["2-3"] == 1
    assert consecutive["draws_with_consecutive"] == 1
    assert consecutive["total_consecutive_pairs"] == 2
    assert consecutive["maximum_consecutive_pairs"] == 2
    assert recency[1] == {"last_seen_draw": 3, "draws_since_seen": 0}
    assert recency[2] == {"last_seen_draw": 2, "draws_since_seen": 1}
    assert recency[6] == {"last_seen_draw": 1, "draws_since_seen": 2}


def test_statistical_service_is_reproducible_and_ignores_input_order():
    draws = [SimpleNamespace(id=2, draw_date=date(2026, 1, 2), main_numbers=[4, 5, 6, 7]), SimpleNamespace(id=1, draw_date=date(2026, 1, 1), main_numbers=[1, 2, 3, 4])]
    assert StatisticalService.analyze(draws) == StatisticalService.analyze(list(reversed(draws)))


def test_statistical_service_handles_empty_and_single_draw_boundaries():
    assert StatisticalService.analyze([]) == {"number_frequency": {}, "number_recency": {}, "even_odd_distribution": {}, "sum_distribution": {"count": 0, "minimum": None, "maximum": None, "average": None}, "pair_frequency": {}, "consecutive_numbers": {"draws_with_consecutive": 0, "total_consecutive_pairs": 0, "maximum_consecutive_pairs": 0}}
    single = StatisticalService.analyze([SimpleNamespace(id=1, draw_date=date(2026, 1, 1), main_numbers=[10])])
    assert single["number_frequency"] == {10: 1}
    assert single["number_recency"] == {10: {"last_seen_draw": 1, "draws_since_seen": 0}}
    assert single["even_odd_distribution"] == {"1-0": 1}
    assert single["sum_distribution"] == {"count": 1, "minimum": 10, "maximum": 10, "average": 10.0}
    assert single["pair_frequency"] == {}
    assert single["consecutive_numbers"] == {"draws_with_consecutive": 0, "total_consecutive_pairs": 0, "maximum_consecutive_pairs": 0}


def test_statistical_service_stays_standby_without_draws():
    class EmptyResult:
        def all(self):
            return []
    class EmptyDb:
        def scalars(self, _statement):
            return EmptyResult()
    assert StatisticalService.overview(EmptyDb()) == {"module_status": "STANDBY", "algorithms_count": 0, "draws_analyzed": 0}


def test_prediction_model_status_is_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    response = client.get("/api/v1/predictions/model-status")
    assert response.status_code == 200
    assert response.json() == {"model_name": "Lotto-Net Gemini AI Core", "version": "not-configured", "status": "UNAVAILABLE"}


def test_prediction_model_status_is_idle_when_key_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    response = client.get("/api/v1/predictions/model-status")
    assert response.status_code == 200
    assert response.json() == {"model_name": "Lotto-Net Gemini AI Core", "version": "gemini-2.5-flash", "status": "IDLE"}
    monkeypatch.setattr(settings, "gemini_api_key", "")


def test_gemini_validator_rejects_out_of_range_numbers():
    valid = {"predictions": [{"numbers": [1, 20, 300, 700, 1000], "confidence_score": 80}]}
    invalid_low = {"predictions": [{"numbers": [0, 20, 300, 700, 1000], "confidence_score": 80}]}
    invalid_high = {"predictions": [{"numbers": [1, 20, 300, 700, 1001], "confidence_score": 80}]}
    assert validate_predictions(valid, expected_count=1) is True
    assert validate_predictions(invalid_low, expected_count=1) is False
    assert validate_predictions(invalid_high, expected_count=1) is False


def test_ai_pattern_insight_accepts_ai_category():
    insight = AiPatternInsight(id="ins-gemini", pattern_name="Análisis de patrones con Gemini", category="IA", weight_percentage=100.0, status="Detectado", description="Structured AI insight")
    assert insight.category == "IA"


def test_ai_prediction_request_rejects_out_of_bounds_parameters():
    for field, value in (("lottery_id", 0), ("prediction_count", 11), ("temperature", 0.0), ("temperature", 1.1), ("min_confidence_threshold", 49), ("min_confidence_threshold", 96)):
        with pytest.raises(ValidationError):
            AiPredictionRequest(**{"lottery_id": 1, field: value})
