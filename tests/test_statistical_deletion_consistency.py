from datetime import date

from sqlalchemy import create_engine, delete, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.lottery_service import LotteryService
from app.services.statistical_service import StatisticalService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def _seed_lottery(db, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def _seed_draw(db, lottery_id: int, source: str, draw_number: str, draw_date: date, numbers: list[int]) -> LotteryDraw:
    draw = LotteryDraw(
        lottery_id=lottery_id,
        source=source,
        draw_number=draw_number,
        draw_date=draw_date,
        main_numbers=numbers,
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    return draw


def _cleanup():
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.commit()
    db.close()


def test_statistics_exclude_deleted_provider_draw_without_affecting_survivor():
    db = TestingSessionLocal()
    try:
        lottery = _seed_lottery(db, "stats-provider-isolation")
        baloto = _seed_draw(
            db, lottery.id, "baloto-colombia", "D-001", date(2026, 9, 1), [1, 2, 3, 4, 5]
        )
        _seed_draw(
            db, lottery.id, "revancha-colombia", "D-001", date(2026, 9, 1), [9, 10, 11, 12, 13]
        )

        before = StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )
        assert before["draws_analyzed"] == 1

        LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)

        after = StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )
        survivor = StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="revancha-colombia"
        )
        assert after == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }
        assert survivor["module_status"] == "READY"
        assert survivor["draws_analyzed"] == 1
    finally:
        db.close()
        _cleanup()


def test_statistics_exclude_all_draws_after_lottery_cascade_delete():
    db = TestingSessionLocal()
    try:
        lottery = _seed_lottery(db, "stats-cascade")
        _seed_draw(
            db, lottery.id, "baloto-colombia", "D-001", date(2026, 9, 1), [1, 2, 3, 4, 5]
        )
        _seed_draw(
            db, lottery.id, "miloto-colombia", "D-002", date(2026, 9, 2), [6, 7, 8, 9, 10]
        )

        assert StatisticalService.overview(db=db, lottery_id=lottery.id)["draws_analyzed"] == 2

        LotteryService.delete_lottery(db=db, lottery_id=lottery.id)

        assert StatisticalService.overview(db=db, lottery_id=lottery.id) == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }
    finally:
        db.close()
        _cleanup()


def test_statistics_for_surviving_lottery_is_unchanged_after_other_lottery_delete():
    db = TestingSessionLocal()
    try:
        first = _seed_lottery(db, "stats-first")
        second = _seed_lottery(db, "stats-second")
        _seed_draw(
            db, first.id, "baloto-colombia", "D-001", date(2026, 9, 1), [1, 2, 3, 4, 5]
        )
        _seed_draw(
            db, second.id, "revancha-colombia", "D-001", date(2026, 9, 1), [9, 10, 11, 12, 13]
        )

        before = StatisticalService.overview(db=db, lottery_id=second.id, source="revancha-colombia")
        LotteryService.delete_lottery(db=db, lottery_id=first.id)
        after = StatisticalService.overview(db=db, lottery_id=second.id, source="revancha-colombia")

        assert before == after == {
            "module_status": "READY",
            "algorithms_count": 6,
            "draws_analyzed": 1,
        }
    finally:
        db.close()
        _cleanup()
