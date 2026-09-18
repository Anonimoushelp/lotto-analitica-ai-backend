from datetime import date

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
        "draws_with_consecutive": 2,
        "total_consecutive_pairs": 6,
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
