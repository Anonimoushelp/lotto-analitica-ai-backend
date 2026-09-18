from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.statistical_service import StatisticalService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def cleanup(db: Session) -> None:
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.commit()


def seed_lottery(db: Session, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def seed_draw(
    db: Session,
    lottery_id: int,
    number: str,
    draw_date: date,
    numbers: list[int],
    source: str,
) -> LotteryDraw:
    draw = LotteryDraw(
        lottery_id=lottery_id,
        draw_number=number,
        draw_date=draw_date,
        main_numbers=numbers,
        source=source,
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    return draw


@pytest.fixture
def db():
    session = SessionLocal()
    cleanup(session)
    yield session
    cleanup(session)
    session.close()


def test_statistics_follow_draw_after_lottery_reassignment(db: Session):
    lottery_a = seed_lottery(db, "PH346-A")
    lottery_b = seed_lottery(db, "PH346-B")
    draw = seed_draw(db, lottery_a.id, "D-001", date(2026, 9, 18), [1, 2, 3], "baloto-colombia")

    before = StatisticalService.analyze([draw], lottery_id=lottery_a.id, source="baloto-colombia")
    assert before["number_frequency"] == {1: 1, 2: 1, 3: 1}
    assert StatisticalService.analyze([draw], lottery_id=lottery_b.id, source="baloto-colombia")["number_frequency"] == {}

    draw.lottery_id = lottery_b.id
    db.commit()

    after_a = StatisticalService.analyze([draw], lottery_id=lottery_a.id, source="baloto-colombia")
    after_b = StatisticalService.analyze([draw], lottery_id=lottery_b.id, source="baloto-colombia")
    assert after_a["number_frequency"] == {}
    assert after_b["number_frequency"] == {1: 1, 2: 1, 3: 1}


def test_overview_isolated_by_lottery_and_source_after_reassignment(db: Session):
    lottery_a = seed_lottery(db, "PH346-C")
    lottery_b = seed_lottery(db, "PH346-D")
    baloto = seed_draw(db, lottery_a.id, "D-010", date(2026, 9, 18), [1, 2, 3], "baloto-colombia")
    revancha = seed_draw(db, lottery_a.id, "D-010", date(2026, 9, 19), [7, 8, 9], "revancha-colombia")
    db.commit()

    baloto.lottery_id = lottery_b.id
    db.commit()

    assert StatisticalService.overview(db, lottery_id=lottery_a.id, source="baloto-colombia")["draws_analyzed"] == 0
    assert StatisticalService.overview(db, lottery_id=lottery_b.id, source="baloto-colombia")["draws_analyzed"] == 1
    assert StatisticalService.overview(db, lottery_id=lottery_a.id, source="revancha-colombia")["draws_analyzed"] == 1
    assert StatisticalService.overview(db, lottery_id=lottery_b.id, source="revancha-colombia")["draws_analyzed"] == 0
    assert revancha.lottery_id == lottery_a.id


def test_reassignment_preserves_provider_statistics_without_cross_contamination(db: Session):
    lottery_a = seed_lottery(db, "PH346-E")
    lottery_b = seed_lottery(db, "PH346-F")
    baloto = seed_draw(db, lottery_a.id, "D-020", date(2026, 9, 18), [1, 2, 3], "baloto-colombia")
    revancha = seed_draw(db, lottery_b.id, "D-020", date(2026, 9, 19), [4, 5, 6], "revancha-colombia")
    baloto.main_numbers = [1, 2, 3]
    db.commit()

    baloto.lottery_id = lottery_b.id
    db.commit()

    baloto_stats = StatisticalService.analyze([baloto, revancha], lottery_id=lottery_b.id, source="baloto-colombia")
    revancha_stats = StatisticalService.analyze([baloto, revancha], lottery_id=lottery_b.id, source="revancha-colombia")
    assert baloto_stats["number_frequency"] == {1: 1, 2: 1, 3: 1}
    assert revancha_stats["number_frequency"] == {4: 1, 5: 1, 6: 1}


def test_statistics_update_is_atomic_on_rollback(db: Session):
    lottery_a = seed_lottery(db, "PH346-G")
    lottery_b = seed_lottery(db, "PH346-H")
    draw = seed_draw(db, lottery_a.id, "D-030", date(2026, 9, 18), [10, 20, 30], "baloto-colombia")
    original = (draw.lottery_id, draw.draw_number, draw.draw_date, list(draw.main_numbers))

    draw.lottery_id = lottery_b.id
    draw.draw_number = "D-031"
    draw.draw_date = date(2026, 9, 19)
    draw.main_numbers = [11, 21, 31]
    db.rollback()

    db.expire_all()
    persisted = db.scalar(select(LotteryDraw).where(LotteryDraw.id == draw.id))
    assert (persisted.lottery_id, persisted.draw_number, persisted.draw_date, persisted.main_numbers) == original
    assert StatisticalService.overview(db, lottery_id=lottery_a.id, source="baloto-colombia")["draws_analyzed"] == 1
    assert StatisticalService.overview(db, lottery_id=lottery_b.id, source="baloto-colombia")["draws_analyzed"] == 0


def test_all_statistical_metrics_follow_updated_numbers_and_dates(db: Session):
    lottery = seed_lottery(db, "PH347-A")
    first = seed_draw(db, lottery.id, "D-040", date(2026, 9, 10), [1, 2, 3, 4], "baloto-colombia")
    second = seed_draw(db, lottery.id, "D-041", date(2026, 9, 17), [2, 4, 6, 8], "baloto-colombia")

    before = StatisticalService.analyze(
        [first, second], lottery_id=lottery.id, source="baloto-colombia"
    )
    assert before["number_frequency"] == {1: 1, 2: 2, 3: 1, 4: 2, 6: 1, 8: 1}
    assert before["sum_distribution"] == {
        "count": 2, "minimum": 10, "maximum": 20, "average": 15.0
    }
    assert before["even_odd_distribution"] == {"2-2": 1, "4-0": 1}
    assert before["number_recency"][2] == {"last_seen_draw": 2, "draws_since_seen": 0}

    first.main_numbers = [9, 10, 11, 12]
    first.draw_date = date(2026, 9, 18)
    db.commit()

    after = StatisticalService.analyze(
        [first, second], lottery_id=lottery.id, source="baloto-colombia"
    )
    assert after["number_frequency"] == {2: 1, 4: 1, 6: 1, 8: 1, 9: 1, 10: 1, 11: 1, 12: 1}
    assert after["sum_distribution"] == {
        "count": 2, "minimum": 20, "maximum": 42, "average": 31.0
    }
    assert after["even_odd_distribution"] == {"2-2": 1, "4-0": 1}
    assert after["pair_frequency"]["9-10"] == 1
    assert "1-2" not in after["pair_frequency"]
    assert after["consecutive_numbers"] == {
        "draws_with_consecutive": 1,
        "total_consecutive_pairs": 3,
        "maximum_consecutive_pairs": 3,
    }
    assert after["number_recency"][9] == {"last_seen_draw": 2, "draws_since_seen": 0}
    assert 1 not in after["number_recency"]


def test_updated_numbers_cannot_contaminate_other_provider_statistics(db: Session):
    lottery = seed_lottery(db, "PH347-B")
    baloto = seed_draw(db, lottery.id, "D-050", date(2026, 9, 15), [1, 2, 3], "baloto-colombia")
    revancha = seed_draw(db, lottery.id, "D-050", date(2026, 9, 16), [7, 8, 9], "revancha-colombia")

    baloto.main_numbers = [10, 20, 30]
    db.commit()

    baloto_stats = StatisticalService.analyze(
        [baloto, revancha], lottery_id=lottery.id, source="baloto-colombia"
    )
    revancha_stats = StatisticalService.analyze(
        [baloto, revancha], lottery_id=lottery.id, source="revancha-colombia"
    )
    assert baloto_stats["number_frequency"] == {10: 1, 20: 1, 30: 1}
    assert revancha_stats["number_frequency"] == {7: 1, 8: 1, 9: 1}
    assert "7-8" not in baloto_stats["pair_frequency"]
    assert "10-20" not in revancha_stats["pair_frequency"]


from types import SimpleNamespace

from app.services.statistical_service import StatisticalInputLimitError


def _fake_draw(numbers: list[int], draw_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=draw_id,
        lottery_id=1,
        source="baloto-colombia",
        draw_number=str(draw_id),
        draw_date=date(2026, 9, 18),
        main_numbers=numbers,
    )


def test_statistics_is_deterministic_for_reordered_historical_input():
    draws = [
        SimpleNamespace(id=30, lottery_id=1, source="legacy-import", draw_number="00010",
                        draw_date=date(2020, 1, 2), main_numbers=[5, 7, 9]),
        SimpleNamespace(id=20, lottery_id=1, source="legacy-import", draw_number="9",
                        draw_date=date(2020, 1, 2), main_numbers=[1, 3, 5]),
        SimpleNamespace(id=10, lottery_id=1, source="legacy-import", draw_number="8",
                        draw_date=date(2020, 1, 1), main_numbers=[2, 4, 6]),
    ]
    assert StatisticalService.analyze(draws) == StatisticalService.analyze(list(reversed(draws)))


def test_statistics_rejects_datetime_as_historical_draw_date():
    draw = _fake_draw([1, 2, 3])
    draw.draw_date = datetime(2026, 9, 18, tzinfo=UTC)
    with pytest.raises(TypeError, match="valid draw_date"):
        StatisticalService.analyze([draw])


@pytest.mark.parametrize(
    "draw_number",
    ["1", "0001", "999999999999999999999999999999999999"],
)
def test_statistics_handles_historical_draw_number_formats_without_integer_overflow(draw_number):
    draw = _fake_draw([1, 2, 3])
    draw.draw_number = draw_number
    result = StatisticalService.analyze([draw])
    assert result["number_frequency"] == {1: 1, 2: 1, 3: 1}


def test_statistics_rejects_non_list_historical_numbers():
    draw = _fake_draw([1, 2, 3])
    draw.main_numbers = "1,2,3"
    with pytest.raises(TypeError, match="main_numbers must be a list"):
        StatisticalService.analyze([draw])


def test_statistics_rejects_boolean_historical_numbers():
    draw = _fake_draw([1, 2, 3])
    draw.main_numbers = [True, 2, 3]
    with pytest.raises(ValueError, match="positive integers"):
        StatisticalService.analyze([draw])


def test_statistics_rejects_more_than_maximum_draws():
    draws = [_fake_draw([1], index) for index in range(10_001)]
    with pytest.raises(StatisticalInputLimitError):
        StatisticalService.analyze(draws)


def test_statistics_rejects_excessive_numbers_per_draw():
    with pytest.raises(StatisticalInputLimitError):
        StatisticalService.analyze([_fake_draw(list(range(1, 102)))])


def test_statistics_rejects_excessive_pair_operations():
    draws = [_fake_draw(list(range(1, 16)), index) for index in range(1, 10_001)]
    with pytest.raises(StatisticalInputLimitError):
        StatisticalService.analyze(draws)


def test_statistics_rejects_excessive_unique_number_cardinality():
    draws = [_fake_draw([index], index) for index in range(1, 10_002)]
    with pytest.raises(StatisticalInputLimitError):
        StatisticalService.analyze(draws)


def test_statistics_rejects_excessive_unique_pair_cardinality():
    draws = [
        _fake_draw(list(range(start, start + 50)), index)
        for index, start in enumerate(range(1, 5_051, 50), start=1)
    ]
    with pytest.raises(StatisticalInputLimitError):
        StatisticalService.analyze(draws)


def test_repeated_correction_reingestion_cycles_keep_single_current_statistical_state(db: Session):
    lottery = seed_lottery(db, "PH370-A")
    draw = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number="70001",
        draw_date=date(2026, 9, 10), main_numbers=[1, 2, 3, 4, 5],
        source="baloto-colombia",
    )
    corrections = [
        ("70002", date(2026, 9, 11), [6, 7, 8, 9, 10]),
        ("70003", date(2026, 9, 12), [11, 12, 13, 14, 15]),
        ("70004", date(2026, 9, 13), [16, 17, 18, 19, 20]),
    ]
    for draw_number, draw_date, numbers in corrections:
        draw = LotteryDrawService.update_draw(
            db=db, draw_id=draw.id,
            update_data={"draw_number": draw_number, "draw_date": draw_date, "main_numbers": numbers},
        )
        with pytest.raises(Exception) as exc_info:
            LotteryDrawService.create_draw(
                db=db, lottery_id=lottery.id, draw_number=draw_number,
                draw_date=draw_date, main_numbers=numbers,
                source="baloto-colombia",
            )
        assert getattr(exc_info.value, "status_code", None) == 409

    rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="baloto-colombia", limit=100
    )
    stats = StatisticalService.analyze(rows, lottery_id=lottery.id, source="baloto-colombia")
    assert len(rows) == 1
    assert rows[0].id == draw.id
    assert stats["number_frequency"] == {16: 1, 17: 1, 18: 1, 19: 1, 20: 1}
    assert 1 not in stats["number_frequency"]
    assert 11 not in stats["number_frequency"]


def test_multiple_scope_cycles_preserve_provider_and_lottery_statistics(db: Session):
    lottery_a = seed_lottery(db, "PH370-B")
    lottery_b = seed_lottery(db, "PH370-C")
    states = [
        (lottery_a.id, "baloto-colombia", [1, 7, 12, 28, 43]),
        (lottery_a.id, "revancha-colombia", [2, 8, 17, 29, 41]),
        (lottery_b.id, "baloto-colombia", [3, 9, 18, 27, 39]),
        (lottery_b.id, "revancha-colombia", [4, 10, 19, 30, 38]),
    ]
    draws = []
    for lottery_id, source, numbers in states:
        draws.append(
            LotteryDrawService.create_draw(
                db=db, lottery_id=lottery_id, draw_number="70010",
                draw_date=date(2026, 9, 14), main_numbers=numbers, source=source,
            )
        )

    for cycle in range(3):
        for index, draw in enumerate(draws):
            base = 50 + cycle * 10 + index * 5
            numbers = [base + offset for offset in range(1, 6)]
            LotteryDrawService.update_draw(
                db=db, draw_id=draw.id,
                update_data={"draw_number": f"700{20 + cycle * 10 + index}",
                             "draw_date": date(2026, 9, 15 + cycle),
                             "main_numbers": numbers},
            )

        if cycle == 1:
            LotteryDrawService.delete_draw(db=db, draw_id=draws[1].id)
            draws[1] = LotteryDrawService.create_draw(
                db=db, lottery_id=lottery_a.id, draw_number="70090",
                draw_date=date(2026, 9, 17), main_numbers=[101, 102, 103, 104, 105],
                source="revancha-colombia",
            )

    expected = {
        (lottery_a.id, "baloto-colombia"): {61: 1, 62: 1, 63: 1, 64: 1, 65: 1},
        (lottery_a.id, "revancha-colombia"): {101: 1, 102: 1, 103: 1, 104: 1, 105: 1},
        (lottery_b.id, "baloto-colombia"): {71: 1, 72: 1, 73: 1, 74: 1, 75: 1},
        (lottery_b.id, "revancha-colombia"): {76: 1, 77: 1, 78: 1, 79: 1, 80: 1},
    }
    for (lottery_id, source), frequency in expected.items():
        rows = LotteryDrawService.list_draws(db=db, lottery_id=lottery_id, source=source, limit=100)
        stats = StatisticalService.analyze(rows, lottery_id=lottery_id, source=source)
        assert len(rows) == 1
        assert stats["number_frequency"] == frequency
