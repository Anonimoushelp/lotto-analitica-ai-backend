from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import require_admin_or_analyst
from app.api.routes.statistics import StatisticalService
from app.main import app
from app.services.statistical_service import StatisticalInputLimitError


def test_statistical_input_limit_returns_413_without_internal_error_leak(monkeypatch):
    def raise_limit(*args, **kwargs):
        raise StatisticalInputLimitError("Statistical analysis input is too large")

    monkeypatch.setattr(StatisticalService, "overview", raise_limit)
    app.dependency_overrides[require_admin_or_analyst] = lambda: object()

    try:
        response = TestClient(app).get("/api/v1/statistics/overview")
    finally:
        app.dependency_overrides.pop(require_admin_or_analyst, None)

    assert response.status_code == 413
    assert response.json() == {"detail": "Statistical analysis input is too large"}
    assert response.headers["X-Request-ID"]


def test_statistical_overview_limits_database_rows_before_analysis():
    class ScalarResult:
        def all(self):
            return [
                SimpleNamespace(
                    draw_date=date(2026, 1, 1),
                    main_numbers=[1],
                    lottery_id=1,
                    id=index,
                )
                for index in range(10_001)
            ]

    class FakeDatabase:
        def __init__(self):
            self.statement = None

        def scalars(self, statement):
            self.statement = statement
            return ScalarResult()

    db = FakeDatabase()

    try:
        StatisticalService.overview(db=db, lottery_id=1)
    except StatisticalInputLimitError as exc:
        assert str(exc) == "Statistical analysis input is too large"
    else:
        raise AssertionError("Expected statistical input limit")

    assert db.statement._limit_clause.value == 10_001
