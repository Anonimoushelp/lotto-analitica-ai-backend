from app.catalog.colombia_lotteries_2026 import (
    COLOMBIA_LOTTERIES_2026,
    LotteryStatus,
    active_ordinary_lotteries,
    get_colombia_lottery,
)


def test_catalog_contains_15_operational_2026_lotteries():
    assert len(COLOMBIA_LOTTERIES_2026) == 15
    assert len(active_ordinary_lotteries()) == 14


def test_ordinary_calendar_weekdays_match_2026_public_schedule():
    expected = {
        "LOTERIA_CUNDINAMARCA": 0,
        "LOTERIA_TOLIMA": 0,
        "LOTERIA_CRUZ_ROJA": 1,
        "LOTERIA_HUILA": 1,
        "LOTERIA_MANIZALES": 2,
        "LOTERIA_VALLE": 2,
        "LOTERIA_META": 2,
        "LOTERIA_BOGOTA": 3,
        "LOTERIA_QUINDIO": 3,
        "LOTERIA_MEDELLIN": 4,
        "LOTERIA_SANTANDER": 4,
        "LOTERIA_RISARALDA": 4,
        "LOTERIA_BOYACA": 5,
        "LOTERIA_CAUCA": 5,
    }
    assert {
        item.code: item.ordinary_weekday
        for item in active_ordinary_lotteries()
    } == expected


def test_extra_colombia_is_not_treated_as_weekly_ordinary():
    extra = get_colombia_lottery("extra_colombia")
    assert extra.status is LotteryStatus.EXTRAORDINARY_ONLY
    assert extra.ordinary_weekday is None


def test_unknown_lottery_is_rejected():
    try:
        get_colombia_lottery("UNKNOWN")
    except KeyError as exc:
        assert "Unknown Colombia lottery" in str(exc)
    else:
        raise AssertionError("Unknown lottery must raise KeyError")
