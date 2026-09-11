from unittest.mock import Mock

from app.services.statistical_service import StatisticalService


def test_overview_fails_closed_until_algorithms_are_implemented():
    db = Mock()
    db.scalar.return_value = 12

    result = StatisticalService.overview(db)

    assert result == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 12,
    }


def test_overview_reports_zero_draws_without_claiming_algorithms():
    db = Mock()
    db.scalar.return_value = None

    result = StatisticalService.overview(db)

    assert result["module_status"] == "STANDBY"
    assert result["algorithms_count"] == 0
    assert result["draws_analyzed"] == 0
