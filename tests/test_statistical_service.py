from datetime import date
from types import SimpleNamespace

import pytest

from app.services.statistical_service import (
    StatisticalInputLimitError,
    StatisticalService,
)


def draw(draw_id, lottery_id, numbers, day, source="test-source"):
    return SimpleNamespace(
        id=draw_id,
        lottery_id=lottery_id,
        draw_type="DEFAULT",
        draw_number=str(draw_id),
        draw_date=date(2026, 9, day),
        main_numbers=numbers,
        source=source,
    )


def test_analysis_is_scoped_by_lottery_and_source():
    draws = [
        draw(1, 1, [1, 2, 3], 1),
        draw(2, 1, [1, 4, 6], 2),
        draw(3, 2, [9, 10, 11], 3),
    ]

    result = StatisticalService.analyze(draws, lottery_id=1, source="test-source")

    assert result["number_frequency"] == {1: 2, 2: 1, 3: 1, 4: 1, 6: 1}
    assert result["sum_distribution"]["count"] == 2
    assert result["consecutive_numbers"]["draws_with_consecutive"] == 1


def test_analysis_is_deterministic_and_tracks_recency():
    draws = [
        draw(2, 1, [1, 4, 6], 2),
        draw(1, 1, [1, 2, 3], 1),
    ]

    result = StatisticalService.analyze(draws, lottery_id=1)

    assert list(result["number_frequency"]) == [1, 2, 3, 4, 6]
    assert result["number_recency"][1] == {
        "last_seen_draw": 2,
        "draws_since_seen": 0,
    }


def test_analysis_rejects_invalid_numbers():
    with pytest.raises(ValueError, match="positive integers"):
        StatisticalService.analyze(
            [draw(1, 1, [0, 2, 3], 1)],
            lottery_id=1,
        )


def test_analysis_rejects_duplicate_numbers():
    with pytest.raises(ValueError, match="duplicate"):
        StatisticalService.analyze(
            [draw(1, 1, [1, 1, 3], 1)],
            lottery_id=1,
        )


def test_analysis_rejects_excessive_pair_work():
    numbers = list(range(1, 100))
    draws = [draw(i, 1, numbers, (i % 28) + 1) for i in range(1, 250)]

    with pytest.raises(StatisticalInputLimitError):
        StatisticalService.analyze(draws, lottery_id=1)
